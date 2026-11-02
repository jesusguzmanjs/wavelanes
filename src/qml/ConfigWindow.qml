import QtQuick 2.15
import QtQuick.Window 2.15

// The settings window, opened by ConfigButton.qml. Changes apply at once and
// are kept by PanelSettings.qml. QML never hides this window: it adds " open"
// to its title while it should be seen, and the placing script shows it over
// the middle of Traktor's window or hides it, as it does with the lane panels.
// Mouse only: Traktor keeps the keyboard for its own shortcuts.
Window {
    id: config
    property PanelSettings settings
    title: "WaveLanes config" + (settings.configOpen ? " open" : "")
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    width: 310
    height: content.implicitHeight + 2
    color: "#3a3a3a"
    visible: true
    // Qt shows the window as soon as it is made, before the placing script
    // finds and hides it: see-through until it is opened, so that nothing
    // flashes when Traktor starts. (Not visible: false, which would leave it
    // without the native window the script looks for.)
    opacity: settings.configOpen ? 1 : 0

    readonly property color textColor: "#e6e6e6"
    readonly property color dimColor: "#8c8c8c"
    readonly property color accent: "#2ba0e0"
    readonly property color warn: "#e0a030"

    FontLoader { id: pragmatica; source: "../../Screens/Fonts/PragmaticaMedium.ttf" }

    component Label: Text {
        font.family: pragmatica.name
        color: config.textColor
        font.pixelSize: 12
    }

    // A section title; line: true draws a line above it.
    component Section: Label {
        property bool line: false
        width: parent.width
        height: 30
        verticalAlignment: Text.AlignBottom
        bottomPadding: 3
        color: config.dimColor
        font.pixelSize: 10
        font.bold: true
        font.letterSpacing: 0.8
        Rectangle {
            y: 6
            width: parent.width
            height: 1
            color: "#333333"
            visible: parent.line
        }
    }

    // A section title, with an on/off switch right after it (switchKey), an
    // (i) with a tooltip after that (info) and controls at its right.
    component SectionHeader: Item {
        id: header
        property string text
        property bool line: false
        property string switchKey: ""
        property string info: ""
        default property alias controls: headerControls.data
        width: parent.width
        // Taller than a plain Section: room for the controls.
        height: 36
        Section {
            id: headerTitle
            height: parent.height
            text: parent.text
            line: parent.line
        }
        Switch {
            id: headerSwitch
            visible: header.switchKey !== ""
            key: header.switchKey !== "" ? header.switchKey : "showLeft"
            x: headerTitle.contentWidth + 10
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
        }
        InfoIcon {
            visible: header.info !== ""
            text: header.info
            x: headerSwitch.visible ? headerSwitch.x + headerSwitch.width + 8 : headerTitle.contentWidth + 8
            anchors.verticalCenter: headerSwitch.verticalCenter
        }
        Row {
            id: headerControls
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
            spacing: 6
        }
    }

    // A framed group of settings.
    component Card: Rectangle {
        default property alias content: cardColumn.data
        width: parent.width
        height: cardColumn.height
        radius: 3
        color: "#232323"
        border.color: "#333333"
        Column {
            id: cardColumn
            x: 10
            width: parent.width - 20
            topPadding: -4
            bottomPadding: 10
        }
    }

    // An on/off switch bound to one settings property, without a label.
    component Switch: Rectangle {
        id: switchBox
        property string key
        readonly property bool on: config.settings[key]
        width: 30
        height: 16
        radius: 8
        color: on ? config.accent : "#252525"
        border.color: on ? config.accent : "#4a4a4a"
        Rectangle {
            x: switchBox.on ? parent.width - width - 2 : 2
            anchors.verticalCenter: parent.verticalCenter
            width: 12
            height: 12
            radius: 6
            color: "#e6e6e6"
        }
        MouseArea {
            anchors.fill: parent
            onClicked: config.settings[switchBox.key] = !switchBox.on
        }
    }

    // An on/off switch for a layout setting, which waits for a restart; blue
    // while it differs from what the launcher applied.
    component RestartToggle: Item {
        id: rtoggle
        property string text
        property string key
        property var onValue: true
        property var offValue: false
        property string tip: ""
        signal toggled
        readonly property bool on: config.settings[key] === onValue
        width: parent.width
        height: 26
        Label {
            anchors.verticalCenter: parent.verticalCenter
            text: rtoggle.text
            color: config.settings.waiting(rtoggle.key) ? config.accent : config.textColor
            Tip { text: rtoggle.tip }
        }
        Rectangle {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: 30
            height: 16
            radius: 8
            color: rtoggle.on ? config.accent : "#252525"
            border.color: rtoggle.on ? config.accent : "#4a4a4a"
            Rectangle {
                x: rtoggle.on ? parent.width - width - 2 : 2
                anchors.verticalCenter: parent.verticalCenter
                width: 12
                height: 12
                radius: 6
                color: "#e6e6e6"
            }
        }
        MouseArea {
            anchors.fill: parent
            onClicked: {
                config.settings[rtoggle.key] = rtoggle.on ? rtoggle.offValue : rtoggle.onValue
                rtoggle.toggled()
            }
        }
    }

    // A small − or + button; held down, it repeats.
    component SmallButton: Rectangle {
        id: small
        property string text
        signal clicked
        width: 22
        height: 20
        radius: 2
        color: smallArea.pressed ? "#4a4a4a" : "#2a2a2a"
        border.color: "#4a4a4a"
        Label {
            anchors.centerIn: parent
            text: small.text
            font.bold: true
        }
        MouseArea {
            id: smallArea
            anchors.fill: parent
            onClicked: small.clicked()
            onPressAndHold: holdTimer.start()
            onReleased: holdTimer.stop()
            onCanceled: holdTimer.stop()
        }
        Timer {
            id: holdTimer
            interval: 70
            repeat: true
            onTriggered: small.clicked()
        }
    }

    // A label with − value + on the right.
    component Stepper: Item {
        id: stepper
        property string text
        property string value
        property bool changed: false
        property string tip: ""
        signal down
        signal up
        width: parent.width
        height: 30
        Label {
            anchors.verticalCenter: parent.verticalCenter
            text: stepper.text
            Tip { text: stepper.tip }
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            SmallButton { text: "−"; onClicked: stepper.down() }
            Label {
                anchors.verticalCenter: parent.verticalCenter
                width: 74
                horizontalAlignment: Text.AlignHCenter
                text: stepper.value
                color: stepper.changed ? config.accent : config.textColor
                font.bold: true
            }
            SmallButton { text: "+"; onClicked: stepper.up() }
        }
    }

    // The slot being chosen, from SlotButton: {panel, row, slot, name, x, y},
    // or null. The list (picker, below) opens under it.
    property var pick: null

    // Tooltips: Tip { text } in an item shows the text under it after a
    // moment with the mouse on it (a HoverHandler, so it takes no clicks).
    property Item tipItem: null
    property string tipText: ""
    property bool tipShown: false
    function hoverTip(item, text, on) {
        if (on && text !== "") {
            tipItem = item
            tipText = text
            tipShown = false
            tipTimer.restart()
        } else if (item === tipItem) {
            tipTimer.stop()
            tipShown = false
            tipItem = null
        }
    }
    Timer {
        id: tipTimer
        interval: 500
        onTriggered: config.tipShown = true
    }
    component Tip: HoverHandler {
        property string text
        onHoveredChanged: config.hoverTip(parent, text, hovered)
    }
    // A small (i) that explains something in its tooltip.
    component InfoIcon: Rectangle {
        property string text
        width: 14
        height: 14
        radius: 7
        color: "transparent"
        border.color: config.dimColor
        Label {
            anchors.centerIn: parent
            text: "i"
            color: config.dimColor
            font.pixelSize: 10
            font.bold: true
        }
        Tip { text: parent.text }
    }
    // The window is hidden by the placing script, not by QML: close the list
    // with it.
    Connections {
        target: config.settings
        function onConfigOpenChanged() { config.pick = null }
    }

    // One slot of a panel: shows its element; a click opens the list.
    component SlotButton: Rectangle {
        id: slotButton
        property string panel
        property int row
        property int slot
        property string name
        // Left out of the panel for room, at the lanes' height now.
        property bool cut: false
        readonly property bool picking: config.pick !== null && config.pick.panel === panel
                                        && config.pick.row === row && config.pick.slot === slot
        height: 24
        radius: 2
        color: slotArea.pressed ? "#333333" : "#262626"
        border.color: picking ? config.accent : cut ? config.warn : slotArea.containsMouse ? "#5a5a5a" : "#3d3d3d"
        Tip { text: slotButton.cut ? "Does not fit the current lane height (" + config.settings.panelHeight + " px)." : "" }
        Label {
            anchors.fill: parent
            anchors.leftMargin: 4
            anchors.rightMargin: 4
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            text: config.settings.elementLabels[slotButton.name]
            color: slotButton.name === "" ? config.dimColor : slotButton.cut ? config.warn : config.textColor
            font.pixelSize: 11
        }
        MouseArea {
            id: slotArea
            anchors.fill: parent
            hoverEnabled: true
            onClicked: {
                var p = slotButton.mapToItem(config.contentItem, 0, slotButton.height)
                config.pick = {panel: slotButton.panel, row: slotButton.row, slot: slotButton.slot,
                               name: slotButton.name, x: p.x, y: p.y}
            }
        }
    }

    // A panel as its rows of two slots; a whole-row element takes both. What
    // does not fit in the lanes as they are now has an amber border, and says
    // so in its tooltip.
    component PanelSlots: Column {
        id: slots
        property string panel
        readonly property var rows: config.settings[panel]
        readonly property var cut: config.settings.panelHeight > 0 ? config.settings.panelPlan(panel).dropped : []
        width: parent.width
        topPadding: 4
        bottomPadding: 6
        spacing: 3
        Rectangle {
            width: parent.width
            height: slotRows.height + 10
            radius: 2
            color: "#1a1a1a"
            border.color: "#333333"
            Column {
                id: slotRows
                x: 5
                y: 5
                width: parent.width - 10
                spacing: 4
                Repeater {
                    model: slots.rows.length
                    Item {
                        id: slotRow
                        readonly property int r: index
                        readonly property var names: slots.rows[index]
                        readonly property bool whole: config.settings.wholeRow.indexOf(names[0]) >= 0
                        width: slotRows.width
                        height: 24
                        Repeater {
                            model: slotRow.whole ? 1 : 2
                            SlotButton {
                                panel: slots.panel
                                row: slotRow.r
                                slot: index
                                name: slotRow.names[index]
                                cut: slots.cut.indexOf(name) >= 0
                                x: index * (slotRow.width + 4) / 2
                                width: slotRow.whole ? slotRow.width : (slotRow.width - 4) / 2
                            }
                        }
                    }
                }
            }
        }
    }

    // A panel's width, in steps of 10, compact for a section header.
    component WidthControl: Row {
        property string key
        readonly property string panel: key === "leftWidth" ? "left" : "right"
        spacing: 4
        Label {
            anchors.verticalCenter: parent.verticalCenter
            text: "Width"
            color: config.dimColor
            font.pixelSize: 10
        }
        SmallButton {
            text: "−"
            onClicked: config.settings.setPanelWidth(parent.panel, config.settings[parent.key] - 10)
        }
        Label {
            anchors.verticalCenter: parent.verticalCenter
            width: 44
            horizontalAlignment: Text.AlignHCenter
            text: config.settings[parent.key] + " px"
            font.pixelSize: 11
            font.bold: true
        }
        SmallButton {
            text: "+"
            onClicked: config.settings.setPanelWidth(parent.panel, config.settings[parent.key] + 10)
        }
    }

    // 1 px border.
    Rectangle {
        anchors.fill: parent
        color: "#1e1e1e"
        border.color: "#4a4a4a"
    }

    Column {
        id: content
        x: 1
        y: 1
        width: parent.width - 2

        // Title bar.
        Rectangle {
            width: parent.width
            height: 32
            color: "#262626"
            Label {
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: "WAVELANES"
                font.pixelSize: 11
                font.bold: true
                font.letterSpacing: 1
            }
            Label {
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: "×"
                color: closeArea.containsMouse ? config.textColor : config.dimColor
                font.pixelSize: 18
            }
            MouseArea {
                id: closeArea
                anchors.right: parent.right
                width: 40
                height: parent.height
                hoverEnabled: true
                onClicked: config.settings.configOpen = false
            }
        }

        Column {
            x: 8
            width: parent.width - 16
            topPadding: 8
            bottomPadding: 10
            spacing: 8

            Card {
                SectionHeader {
                    text: "LEFT PANEL"
                    switchKey: "showLeft"
                    WidthControl { key: "leftWidth"; opacity: config.settings.showLeft ? 1 : 0.4 }
                }
                PanelSlots { panel: "left" }

            }

            // Next to the left panel, or in its place without it;
            // its sections set its width.
            Card {
                SectionHeader {
                    text: "STEMS PANEL"
                    switchKey: "showStems"
                    info: "Replaces Traktor's own stem controls, hidden so the lanes can be laid out freely."
                }
                Item {
                    width: parent.width
                    height: 28
                    opacity: config.settings.showStems ? 1 : 0.4
                    Label {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Sections"
                    }
                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        Repeater {
                            model: [{label: "Volume", key: "stemVolume"}, {label: "Filter", key: "stemFilter"},
                                    {label: "FX", key: "stemFx"}]
                            Rectangle {
                                readonly property bool on: config.settings[modelData.key]
                                width: sectionLabel.width + 16
                                height: 20
                                radius: 2
                                color: on ? Qt.rgba(43 / 255, 160 / 255, 224 / 255, 0.2) : "#262626"
                                border.color: on ? config.accent : "#3d3d3d"
                                Label {
                                    id: sectionLabel
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    color: parent.on ? config.textColor : config.dimColor
                                    font.pixelSize: 11
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: config.settings.showStems
                                    onClicked: config.settings[modelData.key] = !parent.on
                                }
                            }
                        }
                    }
                }
            }

            Card {
                SectionHeader {
                    text: "RIGHT PANEL"
                    switchKey: "showInfo"
                    WidthControl { key: "rightWidth"; opacity: config.settings.showInfo ? 1 : 0.4 }
                }
                PanelSlots { panel: "right"; opacity: config.settings.showInfo ? 1 : 0.4 }
                // MIDI Controls > Button N toggles the right panels.
                Item {
                    width: parent.width
                    height: 32
                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        opacity: config.settings.showInfo ? 1 : 0.4
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Hide with MIDI Button"
                            color: config.dimColor
                            font.pixelSize: 11
                            Tip { text: "In Traktor's Controller Manager, map a MIDI note to MIDI Controls > Button N: it hides and shows the right panels." }
                        }
                        SmallButton {
                            text: "−"
                            onClicked: config.settings.midiButton = Math.max(1, config.settings.midiButton - 1)
                        }
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 14
                            horizontalAlignment: Text.AlignHCenter
                            text: config.settings.midiButton
                            font.bold: true
                        }
                        SmallButton {
                            text: "+"
                            onClicked: config.settings.midiButton = Math.min(8, config.settings.midiButton + 1)
                        }
                    }
                }
            }

            Card {
                // Layout: applied on the next start from WaveLanes.
                Column {
                    id: restartSection
                    width: parent.width
                    readonly property var s: config.settings
                    readonly property bool hideDecks: s.hideDecks
                    readonly property int lanes: s.lanes
                    readonly property int laneHeight: s.laneHeight
                    // The lanes, Traktor's header and global section, the decks if
                    // shown and a usable browser have to fit on the screen.
                    function maxLaneHeight(lanes, hideDecks) {
                        return Math.max(91, Math.floor((Screen.height - 300 - (hideDecks ? 0 : 335)) / lanes))
                    }
                    // A change that leaves less room brings the lane height down to fit.
                    function fitLaneHeight(lanes, hideDecks) {
                        if (laneHeight > maxLaneHeight(lanes, hideDecks))
                            s.laneHeight = maxLaneHeight(lanes, hideDecks)
                    }
                    readonly property var bufferSeconds: ({21: "~48 s", 22: "~95 s", 23: "~190 s", 24: "~380 s"})

                    Section { text: "LAYOUT" }

                    RestartToggle {
                        text: "Hide Track Decks (Only Parallel Full)"
                        key: "hideDecks"
                        tip: "Removes the track decks under the lanes in the Parallel Full layout. All other layouts keep their decks."
                        onToggled: restartSection.fitLaneHeight(restartSection.lanes, restartSection.hideDecks)
                    }
                    RestartToggle {
                        text: "Hide Browser (Only Maximised)"
                        key: "hideBrowser"
                        tip: "Removes the browser under the lanes, and the decks over the maximised browser. The lanes then share the window's height, and the browser only opens maximised, in every layout."
                    }
                    Stepper {
                        text: "Lanes"
                        tip: "With 3, lane D goes; deck D stays."
                        value: parent.lanes
                        changed: parent.s.waiting("lanes")
                        function setLanes(n) {
                            parent.s.lanes = n
                            parent.fitLaneHeight(n, parent.hideDecks)
                        }
                        onDown: setLanes(3)
                        onUp: setLanes(4)
                    }
                    Stepper {
                        // Without the browser the lanes share the window's height.
                        visible: !parent.s.hideBrowser
                        text: "Lane Height (max " + parent.maxLaneHeight(parent.lanes, parent.hideDecks) + ")"
                        tip: "The maximum leaves room on the screen for Traktor's header, the decks if shown, and a usable browser."
                        value: parent.laneHeight + " px"
                        changed: parent.s.waiting("laneHeight")
                        onDown: parent.s.laneHeight = Math.max(91, parent.laneHeight - 1)
                        onUp: parent.s.laneHeight = Math.min(parent.maxLaneHeight(parent.lanes, parent.hideDecks), parent.laneHeight + 1)
                    }
                    Stepper {
                        text: "Waveform Buffer"
                        tip: "How much of the track the waveform keeps sharp; it only shows with the waveform zoomed far out. Each step doubles it, and the memory per deck: 16 MB at ~48 s, 128 MB at ~380 s."
                        value: parent.bufferSeconds[parent.s.waveBuffer] || ""
                        changed: parent.s.waiting("waveBuffer")
                        onDown: parent.s.waveBuffer = Math.max(21, parent.s.waveBuffer - 1)
                        onUp: parent.s.waveBuffer = Math.min(24, parent.s.waveBuffer + 1)
                    }

                    Item {
                        width: parent.width
                        height: 34
                        visible: parent.s.restartPending
                        Label {
                            anchors.left: parent.left
                            anchors.right: discard.left
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            wrapMode: Text.Wrap
                            text: "Pending: quit Traktor and open it with WaveLanes."
                            color: config.accent
                            font.pixelSize: 10
                        }
                        Rectangle {
                            id: discard
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: discardLabel.width + 16
                            height: 20
                            radius: 2
                            color: discardArea.pressed ? "#4a4a4a" : "#2a2a2a"
                            border.color: "#4a4a4a"
                            Label {
                                id: discardLabel
                                anchors.centerIn: parent
                                text: "Discard"
                                font.pixelSize: 11
                            }
                            MouseArea {
                                id: discardArea
                                anchors.fill: parent
                                onClicked: config.settings.discardLayout()
                            }
                        }
                    }
                }
            }

            Label {
                width: parent.width
                topPadding: 0
                wrapMode: Text.Wrap
                readonly property string problem: !config.settings.loaded
                    ? "Cannot read settings.json: open Traktor with WaveLanes. Changes apply but are not saved."
                    : config.settings.saveError
                visible: problem !== ""
                text: problem
                color: "#ff4b4b"
                font.pixelSize: 10
            }

        }
    }

    // The list of elements for the slot being chosen. A click outside closes it.
    MouseArea {
        anchors.fill: parent
        visible: config.pick !== null
        onClicked: config.pick = null
    }
    Rectangle {
        id: picker
        visible: config.pick !== null
        width: 190
        height: pickList.height + 8
        x: config.pick === null ? 0 : Math.max(4, Math.min(config.pick.x, config.width - width - 4))
        y: config.pick === null ? 0 : Math.max(4, Math.min(config.pick.y + 2, config.height - height - 4))
        radius: 3
        color: "#262626"
        border.color: "#4a4a4a"
        Column {
            id: pickList
            x: 4
            y: 4
            width: parent.width - 8
            Repeater {
                model: [""].concat(config.settings.elementNames)
                Rectangle {
                    id: choice
                    readonly property var where: modelData === "" ? null : config.settings.find(modelData)
                    readonly property bool current: config.pick !== null && modelData === config.pick.name
                    width: pickList.width
                    height: 22
                    radius: 2
                    color: choiceArea.containsMouse ? "#333333" : "transparent"
                    Label {
                        anchors.left: parent.left
                        anchors.leftMargin: 6
                        anchors.verticalCenter: parent.verticalCenter
                        text: config.settings.elementLabels[modelData]
                        color: choice.current ? config.accent : modelData === "" ? config.dimColor : config.textColor
                        font.pixelSize: 11
                    }
                    // Where it is now, if elsewhere: it would swap.
                    Label {
                        anchors.right: parent.right
                        anchors.rightMargin: 6
                        anchors.verticalCenter: parent.verticalCenter
                        visible: choice.where !== null && !choice.current
                        text: choice.where === null ? ""
                              : (choice.where.panel === "left" ? "left " : "right ") + (choice.where.row + 1)
                        color: config.dimColor
                        font.pixelSize: 10
                    }
                    MouseArea {
                        id: choiceArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            config.settings.place(config.pick.panel, config.pick.row, config.pick.slot, modelData)
                            config.pick = null
                        }
                    }
                }
            }
        }
    }

    // The tooltip, under the item (above it if there is no room below).
    Rectangle {
        id: tip
        visible: config.tipShown && config.tipItem !== null && config.pick === null
        z: 10
        width: Math.min(tipLabel.implicitWidth, 240) + 16
        height: tipLabel.height + 10
        readonly property point below: config.tipItem === null ? Qt.point(0, 0)
            : config.tipItem.mapToItem(config.contentItem, 0, config.tipItem.height + 3)
        readonly property real above: config.tipItem === null ? 0 : below.y - config.tipItem.height - 6 - height
        x: Math.max(4, Math.min(below.x, config.width - width - 4))
        y: below.y + height <= config.height - 4 ? below.y : Math.max(4, above)
        radius: 3
        color: "#111111"
        border.color: "#4a4a4a"
        Label {
            id: tipLabel
            x: 8
            y: 5
            width: Math.min(implicitWidth, 240)
            wrapMode: Text.Wrap
            text: config.tipText
            color: "#d0d0d0"
            font.pixelSize: 11
        }
    }
}
