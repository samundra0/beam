import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Beam: cast the screen to an AirPlay display. All the work happens in the
// beamctl helper beside this file, which answers every command with JSON;
// this file only draws what it says and passes clicks back to it.
Panel {
  id: root
  moduleName: "beam.cast"
  ipcTarget: "beam.cast"

  // Third-party plugins have no OMARCHY_PATH-style root; resolve our own directory.
  readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl(".")).replace(/^file:\/\//, "")).replace(/\/$/, "")
  readonly property string helper: pluginDir + "/beamctl"

  property var devices: []
  property var network: ({})
  property var checks: []
  property var fixes: []
  property bool doctorOk: true
  property bool discovering: false
  property bool settingUp: false
  property bool firstRunChecked: false
  property string actionError: ""
  property string pendingAction: ""
  property var status: ({ state: "idle" })
  property bool showLog: false
  property int deviceIndex: 0
  property bool cursorActive: false

  readonly property string castState: String(status.state || "idle")
  readonly property bool casting: castState === "live" || castState === "connecting" || castState === "pairing"
  readonly property bool sound: setting("sound", true) === true
  readonly property bool showCursor: setting("cursor", true) === true
  readonly property bool askSource: setting("askSource", true) === true
  readonly property string targetLabel: {
    var host = String(status.host || "")
    for (var i = 0; i < devices.length; i++)
      if (devices[i].host === host) return String(devices[i].name)
    return String(status.name || "") || host
  }
  readonly property var firewall: status.firewall || ({})

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function stateText() {
    if (pendingAction === "start") return strings.t("state.starting")
    if (pendingAction === "firewall-close") return strings.t("state.closingFirewall")
    if (pendingAction === "change-source") return strings.t("state.changingSource")
    if (castState === "live")
      return status.external ? strings.t("state.liveExternal").arg(targetLabel) : strings.t("state.live").arg(targetLabel)
    if (castState === "connecting") return strings.t("state.connecting")
    if (castState === "pairing") return strings.t("state.pairing")
    if (castState === "failed") return strings.t("state.failed")
    return strings.t("state.idle")
  }

  function parse(text) {
    try { return JSON.parse(text) } catch (e) { return null }
  }

  function refreshStatus() { if (!statusProc.running) statusProc.running = true }
  function refreshDoctor() { if (!doctorProc.running) doctorProc.running = true }
  function discover() {
    if (discoverProc.running) return
    discovering = true
    discoverProc.running = true
  }

  function runAction(args) {
    if (actionProc.running) return
    actionError = ""
    pendingAction = String(args[0])
    actionProc.command = ["python3", helper].concat(args)
    actionProc.running = true
  }

  // choose forces Hyprland's screen-share picker even when "Ask what to share
  // each time" is off.
  function cast(device, code, choose) {
    if (!device || !device.host) return
    var args = ["start", String(device.host), String(device.port), "--name", String(device.name || "")]
    if (device.deviceId) args.push("--device-id", String(device.deviceId))
    if (sound) args.push("--audio")
    if (!showCursor) args.push("--no-cursor")
    if (askSource || choose) args.push("--choose")
    if (code) args.push("--code", code)
    runAction(args)
  }

  function stop() { runAction(["stop"]) }

  function pair(code) {
    var device = { host: status.host, port: status.port, name: status.name, deviceId: "" }
    for (var i = 0; i < devices.length; i++)
      if (devices[i].host === status.host) device = devices[i]
    cast(device, code)
  }

  function setOption(name, value) {
    var next = Object.assign({}, root.settings)
    next[name] = value
    root.settings = next
    if (root.bar && root.bar.shell) root.bar.shell.updateEntryInline(root.moduleName, root.settings)
  }

  function activateSelected() {
    if (deviceIndex < 0 || deviceIndex >= devices.length) return
    var d = devices[deviceIndex]
    if (casting && status.host === d.host) stop()
    else if (!casting && d.reachable) cast(d, "")
  }

  onOpenedChanged: {
    if (!opened) return
    cursorActive = false
    refreshStatus()
    refreshDoctor()
    discover()
  }

  Process {
    id: statusProc
    command: ["python3", root.helper, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var s = root.parse(text)
        if (s && s.ok) root.status = s
      }
    }
  }

  Process {
    id: doctorProc
    command: ["python3", root.helper, "doctor"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var d = root.parse(text)
        if (!d) return
        root.checks = d.checks || []
        root.fixes = d.fixes || []
        root.doctorOk = d.ok === true
        root.network = d.network || {}
        // Omarchy has no post-install hook, so the first load after install
        // offers setup itself; beamctl remembers it did, so this happens once.
        if (!root.doctorOk && !root.firstRunChecked) {
          root.firstRunChecked = true
          firstRunProc.running = true
        }
      }
    }
  }

  Process {
    id: firstRunProc
    command: ["python3", root.helper, "first-run"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var r = root.parse(text)
        if (r && r.launched === true) root.settingUp = true
      }
    }
  }

  Component.onCompleted: refreshDoctor()

  Process {
    id: discoverProc
    command: ["python3", root.helper, "discover"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var d = root.parse(text)
        root.discovering = false
        if (!d || !d.ok) return
        root.devices = d.devices || []
        root.network = d.network || root.network
        if (root.deviceIndex >= root.devices.length) root.deviceIndex = 0
      }
    }
    onExited: root.discovering = false
  }

  Process {
    id: actionProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var r = root.parse(text)
        if (r && r.ok === false) root.actionError = String(r.error || "")
      }
    }
    onExited: {
      root.pendingAction = ""
      root.refreshStatus()
      root.refreshDoctor()
    }
  }

  // While the setup terminal is open, recheck so the warnings clear by
  // themselves when it finishes (or give up after five minutes).
  Timer {
    id: setupPoll
    interval: 3000
    repeat: true
    running: root.settingUp
    property int ticks: 0
    onRunningChanged: ticks = 0
    onTriggered: {
      ticks++
      root.refreshDoctor()
      if (root.doctorOk || ticks > 100) root.settingUp = false
    }
  }

  // Fast while the panel is open or a cast is starting, slow otherwise so the
  // bar icon still notices a cast that was started or ended elsewhere.
  Timer {
    interval: root.opened || root.castState === "connecting" || root.castState === "pairing" ? 2000 : 10000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refreshStatus()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // Nerd Font cast / cast-connected glyphs.
    text: root.castState === "live" ? "\u{F0119}" : "\u{F0118}"
    active: root.casting
    activeColor: Commons.Color.accent
    tooltipText: root.opened ? "" : (root.castState === "live" ? strings.t("tooltip.live").arg(root.targetLabel) : strings.t("tooltip.idle"))
    onPressed: function(b) {
      if (b === Qt.RightButton && root.casting) root.stop()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight)

    content: PanelKeyCatcher {
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) { root.cursorActive = true; return }
        if (dy !== 0 && root.devices.length > 0)
          root.deviceIndex = Math.max(0, Math.min(root.devices.length - 1, root.deviceIndex + dy))
      }
      onActivateRequested: if (root.cursorActive) root.activateSelected()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(12)

        // ---------- Hero ----------
        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, stopButton.implicitHeight)

          Label {
            id: heroIcon
            text: button.text
            color: root.casting ? Commons.Color.accent : root.bar.foreground
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: stopButton.visible ? stopButton.left : parent.right
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Label {
              text: strings.t("title")
              font.pixelSize: Style.font.title
              font.bold: true
              width: parent.width
            }
            Label {
              text: root.stateText().toUpperCase()
              wrapMode: Text.Wrap
              elide: Text.ElideNone
              maximumLineCount: 2
              opacity: 0.7
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
              width: parent.width
            }
          }

          Button {
            id: stopButton
            visible: root.casting
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: strings.t("screens.stop")
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            onClicked: root.stop()
          }
        }

        Label {
          width: parent.width
          opacity: 0.7
          font.pixelSize: Style.font.bodySmall
          text: root.network && root.network.ssid
            ? strings.t("network.wifi").arg(String(root.network.ssid)).arg(String(root.network.ip || ""))
            : root.network && root.network.ip
              ? strings.t("network.wired").arg(String(root.network.iface || "")).arg(String(root.network.ip))
              : strings.t("network.none")
        }

        // ---------- Firewall ----------
        // While casting, the screen's address is let through UDP 60000-60010;
        // the rule goes when the cast ends. One left behind (a logout mid-cast)
        // is shown here so it can be closed.
        Label {
          visible: root.firewall.host !== undefined && !root.firewall.stale
          width: parent.width
          opacity: 0.6
          wrapMode: Text.Wrap
          elide: Text.ElideNone
          font.pixelSize: Style.font.caption
          text: strings.t("firewall.open").arg(String(root.firewall.host || ""))
        }
        Column {
          visible: root.firewall.stale === true
          width: parent.width
          spacing: Style.space(6)
          Label {
            width: parent.width
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            color: Commons.Color.urgent
            font.pixelSize: Style.font.bodySmall
            text: strings.t("firewall.stale").arg(String(root.firewall.host || ""))
          }
          Button {
            text: strings.t("firewall.close")
            enabled: !actionProc.running
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            onClicked: root.runAction(["firewall-close"])
          }
        }

        // ---------- Errors and pairing ----------
        Label {
          visible: text !== ""
          width: parent.width
          color: Commons.Color.urgent
          wrapMode: Text.Wrap
          elide: Text.ElideNone
          maximumLineCount: 4
          font.pixelSize: Style.font.bodySmall
          text: root.actionError !== "" ? root.actionError
            : (root.castState === "failed" && !root.status.needsCode ? String(root.status.lastError || "") : "")
        }

        Column {
          visible: root.castState === "failed" && root.status.needsCode === true
          width: parent.width
          spacing: Style.space(8)

          Label {
            width: parent.width
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            font.pixelSize: Style.font.bodySmall
            text: strings.t("pin.prompt")
          }
          Row {
            width: parent.width
            spacing: Style.space(8)
            TextField {
              id: pinField
              width: parent.width - pairButton.width - parent.spacing
              placeholderText: strings.t("pin.placeholder")
              foreground: root.bar.foreground
              inputMethodHints: Qt.ImhDigitsOnly
              maximumLength: 16
              onAccepted: if (text !== "") root.pair(text)
            }
            Button {
              id: pairButton
              text: strings.t("pin.pair")
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              enabled: pinField.text !== ""
              onClicked: root.pair(pinField.text)
            }
          }
        }

        // ---------- Setup ----------
        Column {
          visible: !root.doctorOk
          width: parent.width
          spacing: Style.space(8)

          PanelSeparator { foreground: root.bar.foreground }
          PanelSectionHeader {
            text: strings.t("setup.header")
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Repeater {
            model: root.checks
            Column {
              required property var modelData
              visible: !modelData.ok && !modelData.optional
              width: column.width
              spacing: Style.space(2)
              Label { text: "\u{F0028}  " + String(modelData.label); font.pixelSize: Style.font.body; width: parent.width }
              Label { text: String(modelData.detail); opacity: 0.6; font.pixelSize: Style.font.caption; width: parent.width }
            }
          }

          Row {
            spacing: Style.space(8)
            // One button for everything setup needs: it opens a terminal that
            // downloads doubletake and runs the sudo steps, recording each
            // change for uninstall. The panel rechecks while it runs.
            Button {
              text: root.settingUp ? strings.t("setup.running") : strings.t("setup.run")
              enabled: !actionProc.running
              active: true
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              onClicked: { root.settingUp = true; root.runAction(["fix"]) }
            }
            Button {
              text: strings.t("setup.recheck")
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              onClicked: root.refreshDoctor()
            }
          }
        }

        // ---------- Screens ----------
        PanelSeparator { foreground: root.bar.foreground }

        Item {
          width: parent.width
          implicitHeight: Math.max(screensHeader.implicitHeight, rescan.implicitHeight)
          PanelSectionHeader {
            id: screensHeader
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: strings.t("screens.header")
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }
          PanelActionButton {
            id: rescan
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            iconText: "\u{F0450}"
            tooltipText: strings.t("screens.rescan")
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !root.discovering
            onClicked: root.discover()
          }
        }

        Label {
          visible: root.devices.length === 0
          width: parent.width
          opacity: 0.6
          font.pixelSize: Style.font.bodySmall
          text: root.discovering ? strings.t("screens.searching") : strings.t("screens.none")
        }

        Repeater {
          model: root.devices
          Rectangle {
            id: row
            required property var modelData
            required property int index
            readonly property bool current: root.casting && root.status.host === modelData.host
            readonly property bool selected: root.cursorActive && root.deviceIndex === index
            width: column.width
            implicitHeight: rowContent.implicitHeight + Style.space(12)
            radius: Style.cornerRadius
            color: selected ? Qt.rgba(root.bar.foreground.r, root.bar.foreground.g, root.bar.foreground.b, 0.08) : "transparent"

            Column {
              id: rowContent
              anchors.left: parent.left
              anchors.leftMargin: Style.space(8)
              anchors.right: chooseButton.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)
              Label {
                text: String(row.modelData.name)
                font.pixelSize: Style.font.body
                font.bold: row.current
                color: row.current ? Commons.Color.accent : root.bar.foreground
                width: parent.width
              }
              Label {
                text: [String(row.modelData.model || ""), String(row.modelData.host) + ":" + String(row.modelData.port),
                       row.modelData.reachable ? "" : strings.t("screens.unreachable")].filter(function(s) { return s !== "" }).join(" · ")
                opacity: 0.6
                font.pixelSize: Style.font.caption
                width: parent.width
              }
            }

            Button {
              id: chooseButton
              anchors.right: castButton.left
              anchors.rightMargin: Style.space(6)
              anchors.verticalCenter: parent.verticalCenter
              text: strings.t("screens.choose")
              // Idle: cast with the picker. Casting here: restart this cast with
              // the picker to share something else.
              enabled: !actionProc.running && (row.current || (!root.casting && row.modelData.reachable))
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              onClicked: row.current ? root.runAction(["change-source"]) : root.cast(row.modelData, "", true)
            }

            Button {
              id: castButton
              anchors.right: parent.right
              anchors.rightMargin: Style.space(4)
              anchors.verticalCenter: parent.verticalCenter
              text: row.current ? strings.t("screens.stop") : strings.t("screens.cast")
              enabled: row.current || (!root.casting && row.modelData.reachable && !actionProc.running)
              active: row.current
              hasCursor: row.selected
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              onClicked: row.current ? root.stop() : root.cast(row.modelData, "")
              onHovered: function(h) { if (h) { root.cursorActive = true; root.deviceIndex = row.index } }
            }
          }
        }

        // ---------- Options ----------
        PanelSeparator { foreground: root.bar.foreground }

        OptionRow {
          label: strings.t("options.sound")
          checked: root.sound
          onToggled: root.setOption("sound", !root.sound)
        }
        OptionRow {
          label: strings.t("options.cursor")
          checked: root.showCursor
          onToggled: root.setOption("cursor", !root.showCursor)
        }
        OptionRow {
          label: strings.t("options.askSource")
          checked: root.askSource
          onToggled: root.setOption("askSource", !root.askSource)
        }

        // Uninstall runs in a terminal: it asks before changing anything and
        // needs sudo to remove what setup installed.
        Button {
          text: strings.t("uninstall")
          enabled: !actionProc.running
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          bordered: true
          onClicked: root.runAction(["uninstall", "--terminal"])
        }

        // ---------- Log ----------
        Button {
          visible: String(root.status.log || "") !== ""
          text: root.showLog ? strings.t("log.hide") : strings.t("log.show")
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          onClicked: root.showLog = !root.showLog
        }

        Rectangle {
          visible: root.showLog && String(root.status.log || "") !== ""
          width: parent.width
          height: Math.min(logText.implicitHeight + Style.space(12), Style.space(180))
          radius: Style.cornerRadius
          clip: true
          color: Qt.rgba(root.bar.foreground.r, root.bar.foreground.g, root.bar.foreground.b, 0.06)
          Text {
            id: logText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: Style.space(6)
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            text: String(root.status.log || "")
            color: root.bar.foreground
            opacity: 0.8
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }

  // Every string here can come from the network (screen names) or a log, so
  // it is always drawn as plain text.
  component Label: Text {
    textFormat: Text.PlainText
    color: root.bar ? root.bar.foreground : Commons.Color.foreground
    font.family: root.bar ? root.bar.fontFamily : Style.font.family
    elide: Text.ElideRight
    wrapMode: Text.NoWrap
  }

  component OptionRow: Item {
    id: option
    property string label: ""
    property bool checked: false
    signal toggled()
    width: parent ? parent.width : 0
    implicitHeight: Math.max(optionLabel.implicitHeight, optionSwitch.implicitHeight)
    Label {
      id: optionLabel
      anchors.left: parent.left
      anchors.right: optionSwitch.left
      anchors.verticalCenter: parent.verticalCenter
      text: option.label
      font.pixelSize: Style.font.body
    }
    ToggleSwitch {
      id: optionSwitch
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      checked: option.checked
      foreground: root.bar ? root.bar.foreground : Commons.Color.foreground
      onToggled: option.toggled()
    }
  }
}
