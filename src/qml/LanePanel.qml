import CSI 1.0
import QtQuick 2.15
import QtQuick.Window 2.15

import "../../Defines"

// Overlays for one parallel waveform lane: this window, at the lane's left
// end (after Traktor's deck letter), a second one (info, below) at its right
// end, and a third (stemsWin) with the stems; what the first two show is
// chosen in the settings window. They are placed over the lane by
// wave_height_mac.js (wave_height.js on Windows), which finds them by their
// title. BPM, key and loop size step with the wheel or with a
// left/right click; a hotcue works as Traktor's hotcue buttons and is deleted
// with a right click. Colours follow Traktor's (Screens/Defines/Colors.qml) and
// the font is the one Traktor ships for its controller screens.
Window {
    id: win
    property int deckId: 0
    // PanelSettings.qml, shared by every lane: what to show, set from the
    // settings window.
    property PanelSettings settings
    readonly property int appDeck: deckId + 1
    readonly property string deckLetter: String.fromCharCode(65 + deckId)
    readonly property string pathPrefix: "app.traktor.decks." + appDeck + "."

    // The title also tells the placing script that the browser is maximised
    // over the lanes, so that it hides the panels, or that this panel is to
    // stay hidden (leftHidden); the deck letter stays right after the prefix.
    title: "TraktorLanePanel " + deckLetter + (leftHidden ? " hidden" : "") + (browserFullScreen.value ? " browser" : "")
    // No drop shadow: macOS draws it as a light outline round the window,
    // which shows over the lane's borders. The other two windows take these.
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
    width: settings.leftWidth
    height: 212
    // Traktor's lane background, #191919 on screen: macOS shows a Qt window's
    // colour a little lighter (#1a1a1a showed as #1c1c1c, #171717 as
    // #181818). The other two windows take this.
    color: "#181818"
    visible: true

    FontLoader { id: pragmatica; source: "../../Screens/Fonts/PragmaticaMedium.ttf" }

    readonly property color textColor: "#e6e6e6"
    readonly property color dimColor: "#8c8c8c"
    readonly property color lineColor: "#2b2b2b"
    readonly property color masterColor: "#2ba0e0"
    readonly property color syncColor: "#ff8a1f"
    readonly property color loopColor: "#3ddc5a"

    AppProperty { id: isLoaded;         path: pathPrefix + "is_loaded" }
    // The deck's flavour, as in the Controller Manager: 0 Track, 2 Stem (seen
    // on Traktor 4.5.0; the CSI enum decktype is not reachable here).
    AppProperty { id: deckType;         path: pathPrefix + "type" }
    AppProperty { id: trackTitle;       path: pathPrefix + "content.title" }
    AppProperty { id: trackArtist;      path: pathPrefix + "content.artist" }
    // Milliseconds from the start of the track to the beatgrid's first beat.
    AppProperty { id: gridOffset;       path: pathPrefix + "content.grid_offset" }
    // A trigger: makes this deck the tempo master, as Traktor's MASTER button.
    AppProperty { id: setAsMaster;      path: pathPrefix + "set_as_master" }
    // Seconds, seconds, and ms (-1 past the last cue): read as in the
    // Performance Display project (NativeDeckPanel.qml).
    AppProperty { id: trackLength;      path: pathPrefix + "track.content.track_length" }
    AppProperty { id: elapsedTime;      path: pathPrefix + "track.player.elapsed_time" }
    AppProperty { id: nextCuePoint;     path: pathPrefix + "track.player.next_cue_point" }
    AppProperty { id: baseBpm;          path: pathPrefix + "tempo.base_bpm" }
    AppProperty { id: tempoRatio;       path: pathPrefix + "tempo.tempo_for_display" }
    AppProperty { id: adjustBpm;        path: pathPrefix + "tempo.adjust_bpm" }
    AppProperty { id: syncEnabled;      path: pathPrefix + "sync.enabled" }
    AppProperty { id: masterDeckId;     path: "app.traktor.masterclock.source_id" }
    AppProperty { id: browserFullScreen; path: "app.traktor.browser.full_screen" }
    AppProperty { id: loopActive;       path: pathPrefix + "loop.active" }
    AppProperty { id: loopSize;         path: pathPrefix + "loop.size" }
    AppProperty { id: resultingKey;     path: pathPrefix + "track.key.resulting.precise" }
    AppProperty { id: keyAdjust;        path: pathPrefix + "track.key.adjust" }
    AppProperty { id: keyLock;          path: pathPrefix + "track.key.lock_enabled" }
    // Triggers, same as Beatgrid "BPM x2" / "BPM /2" in the Controller Manager.
    AppProperty { id: doubleBpm;        path: pathPrefix + "track.grid.double_bpm" }
    AppProperty { id: halfBpm;          path: pathPrefix + "track.grid.half_bpm" }
    // Hotcue actions take the hotcue index, 0-7, as the X1 MK3 mapping does.
    AppProperty { id: selectOrSetHotcue; path: pathPrefix + "track.cue.select_or_set_hotcue" }
    AppProperty { id: deleteHotcue;      path: pathPrefix + "track.cue.delete_hotcue" }

    readonly property bool isMaster: Number(masterDeckId.value) === deckId

    // select_or_set_hotcue holds a hotcue index (0-7) while its button is
    // down. Its idle value is not known for sure: the one found before a
    // press, unless that is an index (left by a press never let go), else -1.
    property var hotcueIdle: -1
    function hotcueDown(i) {
        var v = selectOrSetHotcue.value
        if (typeof v === "number" && (v < 0 || v > 7)) hotcueIdle = v
        selectOrSetHotcue.value = i
    }
    function hotcueUp() {
        selectOrSetHotcue.value = hotcueIdle
    }


    // A MIDI note mapped in the Controller Manager to MIDI Controls > Button N
    // (4 by default: the one that showed or hid the right strip in the
    // Performance Display project) hides or shows the info panels of every
    // lane, as does the settings window. The panels only say so in their
    // title; the placing script hides the window.
    property bool midiHidden: false
    readonly property bool infoHidden: midiHidden || !settings.showInfo
    // Shown or not from the settings window.
    readonly property bool leftHidden: !settings.showLeft
    AppProperty {
        id: midiToggleInfo
        path: "app.traktor.midi.buttons." + win.settings.midiButton
        onValueChanged: if (value === 1 || value === true) win.midiHidden = !win.midiHidden
    }

    // key.adjust counts in octaves: one semitone is 1/12.
    readonly property int semitoneShift: Math.round(Number(keyAdjust.value || 0) * 12)

    function stepBpm(delta) {
        if (isLoaded.value) adjustBpm.value = Number(adjustBpm.value) + delta * 0.01
    }

    function stepKey(delta) {
        if (!isLoaded.value) return
        var s = Math.max(-12, Math.min(12, semitoneShift + delta))
        if (!keyLock.value) keyLock.value = true
        keyAdjust.value = s / 12
    }

    // Open Key wheel palette, from NativeDeckPanel.qml.
    function keyColor(k) {
        var m = String(k).match(/^(\d+)([md])$/i)
        if (!m) return dimColor
        var major = ["", "#b45aa6", "#7f6caf", "#5588c7", "#3fb9df", "#59bdc9", "#49b58f",
                     "#72b72f", "#98c900", "#ffd21a", "#fb8c29", "#f26732", "#ef4c4f"]
        var minor = ["", "#c58bbd", "#9b89bd", "#82a8cf", "#8ccddd", "#7fc6cb", "#7ac8ab",
                     "#8bc957", "#b2d044", "#ffd84d", "#f6a24c", "#f58a63", "#f3787a"]
        return (m[2].toLowerCase() === "m" ? minor : major)[Number(m[1])]
    }

    // Hotcue type colours: cue, fade in, fade out, load, grid, loop.
    readonly property var hotcueColors: ["#2ba0e0", "#ff7800", "#ff7800", "#ffd200", "#e6e6e6", "#3ddc5a"]

    function bpmText() {
        var b = Number(baseBpm.value), t = Number(tempoRatio.value)
        if (!isFinite(b)) return "—"
        if (!isFinite(t) || t === 0) t = 1
        return (b * t).toFixed(1)
    }

    function pitchText() {
        var t = Number(tempoRatio.value)
        if (!isFinite(t) || t === 0) t = 1
        var p = (t - 1) * 100
        if (Math.abs(p) < 0.005) p = 0
        return (p > 0 ? "+" : "") + p.toFixed(2) + "%"
    }

    function timeText(seconds) {
        var total = Math.floor(Math.max(0, seconds))
        var sec = total % 60
        return Math.floor(total / 60) + ":" + (sec < 10 ? "0" : "") + sec
    }

    function remainingTime() {
        var len = Number(trackLength.value), elapsed = Number(elapsedTime.value)
        return Math.max(0, (isFinite(len) ? len : 0) - (isFinite(elapsed) ? elapsed : 0))
    }

    // Beats to the next cue, or to the end of the track past the last one, as
    // phrase.bar.beat counting down (4 beats a bar, 4 bars a phrase).
    function beatsToCueText() {
        var elapsed = Number(elapsedTime.value), bpm = Number(baseBpm.value)
        var len = Number(trackLength.value), next = Number(nextCuePoint.value)
        if (!isFinite(elapsed) || !(bpm > 0) || !(len > 0)) return ""
        var targetMs = isFinite(next) && next >= 0 ? next : len * 1000
        var diffMs = targetMs - elapsed * 1000
        if (diffMs < 0) return ""
        var beats = Math.floor(diffMs * bpm / 60000 + 0.0001)  // float rounding
        return "- " + (Math.floor(beats / 16) + 1) + "." + (Math.floor(beats / 4) % 4 + 1) + "." + (beats % 4 + 1)
    }

    // The beat the playhead is on, counted from the beatgrid's first beat, as
    // phrase.bar.beat (4 beats a bar, 4 bars a phrase), negative before it:
    // the same as the beat counter of Traktor's own deck header (S8 screens).
    function beatCounterText() {
        var elapsed = Number(elapsedTime.value), bpm = Number(baseBpm.value), offset = Number(gridOffset.value)
        if (!isFinite(elapsed) || !(bpm > 0)) return ""
        var beat = (elapsed * 1000 - (isFinite(offset) ? offset : 0)) * bpm / 60000
        var n = Math.floor(Math.abs(beat))
        return (beat < 0 ? "- " : "") + (Math.floor(n / 16) + 1) + "." + (Math.floor(n / 4) % 4 + 1) + "." + (n % 4 + 1)
    }

    readonly property var loopNames: ["1/32", "1/16", "1/8", "1/4", "1/2", "1", "2", "4", "8", "16", "32"]

    function stepLoop(delta) {
        var v = Number(loopSize.value)
        if (!isFinite(v)) v = 7
        loopSize.value = Math.max(0, Math.min(loopNames.length - 1, v + delta))
    }

    readonly property real remaining: remainingTime()

    // Left click or wheel down steps down, right click or wheel up steps up.
    component Stepper: MouseArea {
        property var step
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: step(mouse.button === Qt.LeftButton ? -1 : 1)
        onWheel: step(wheel.angleDelta.y > 0 ? 1 : -1)
    }

    component Label: Text {
        font.family: pragmatica.name
        color: win.textColor
    }

    // The elements the panels are made of, by name (their sizes are in
    // PanelSettings.elementSpecs). Each is created by a Loader in a panel
    // (PanelBody.qml); the components are defined here so they see this
    // file's ids.
    readonly property var components: ({
        title: titleElement, bpmPitch: bpmPitchElement, bpm: bpmElement, bpmButtons: bpmButtonsElement,
        key: keyElement, loop: loopElement, time: timeElement, beats: beatsElement, cues: cuesElement,
        artist: artistElement, elapsed: elapsedElement, beatCounter: beatCounterElement,
        syncMaster: syncMasterElement
    })

    // Lane A's panel height, for the settings window to show what does not fit.
    onHeightChanged: if (deckId === 0 && settings) settings.panelHeight = height

    // Track title.
    Component {
        id: titleElement
        Label {
            width: parent ? parent.cellWidth : 0
            height: 20
            verticalAlignment: Text.AlignVCenter
            text: isLoaded.value ? (trackTitle.value || "") : ""
            elide: Text.ElideRight
            font.pixelSize: 13
        }
    }

    // BPM, with the pitch over it or the room for it left empty, so that it
    // sits the same either way.
    component BpmBlock: Item {
        property bool pitch: true
        width: 51
        height: 35
        Column {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            Label {
                height: 14
                text: isLoaded.value && pitch ? win.pitchText() : ""
                color: win.dimColor
                font.pixelSize: 11
            }
            Label {
                height: 21
                verticalAlignment: Text.AlignVCenter
                text: isLoaded.value ? win.bpmText() : "—"
                color: !isLoaded.value ? "#5c5c5c"
                     : win.isMaster ? win.masterColor
                     : syncEnabled.value ? win.syncColor : win.textColor
                font.pixelSize: 17
            }
        }
        Stepper { anchors.fill: parent; step: win.stepBpm }
    }
    Component { id: bpmPitchElement; BpmBlock { pitch: true } }
    Component { id: bpmElement; BpmBlock { pitch: false } }

    // Beatgrid x2 and /2.
    Component {
        id: bpmButtonsElement
        Column {
            width: 26
            height: 39
            spacing: 3
            Repeater {
                model: [{label: "x2", prop: doubleBpm}, {label: "/2", prop: halfBpm}]
                Rectangle {
                    width: 26
                    height: 18
                    radius: 2
                    visible: isLoaded.value
                    color: area.pressed ? "#333333" : "#242424"
                    border.color: "#333333"
                    Label {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: "#b3b3b3"
                        font.pixelSize: 10
                        font.bold: true
                    }
                    MouseArea {
                        id: area
                        anchors.fill: parent
                        onClicked: modelData.prop.value = true
                    }
                }
            }
        }
    }

    // Key with its semitone shift over it, as the pitch over the BPM, or the
    // room for it left empty.
    Component {
        id: keyElement
        Item {
            width: 41
            height: 35
            Column {
                id: keyColumn
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                readonly property color keyCol: win.keyColor(resultingKey.value)
                Label {
                    height: 14
                    text: !isLoaded.value || win.semitoneShift === 0 ? "" : (win.semitoneShift > 0 ? "+" : "") + win.semitoneShift
                    color: keyColumn.keyCol
                    font.pixelSize: 11
                    font.bold: true
                }
                Label {
                    height: 21
                    verticalAlignment: Text.AlignVCenter
                    text: isLoaded.value ? (resultingKey.value || "—") : "—"
                    color: keyColumn.keyCol
                    font.pixelSize: 17
                }
            }
            Stepper { anchors.fill: parent; step: win.stepKey }
        }
    }

    // Loop size under a small LOOP, as the pitch over the BPM; green while a
    // loop is on.
    Component {
        id: loopElement
        Rectangle {
            width: loopColumn.width + 12
            height: 35
            radius: 2
            color: loopActive.value ? Qt.rgba(61 / 255, 220 / 255, 90 / 255, 0.14) : "#202020"
            border.color: loopActive.value ? win.loopColor : "#2e2e2e"
            Column {
                id: loopColumn
                anchors.centerIn: parent
                Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: 11
                    verticalAlignment: Text.AlignVCenter
                    text: "LOOP"
                    color: loopActive.value ? "#8fe9a3" : win.dimColor
                    font.pixelSize: 9
                    font.bold: true
                    font.letterSpacing: 0.6
                }
                Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: 19
                    verticalAlignment: Text.AlignVCenter
                    text: win.loopNames[Number(loopSize.value)] || "—"
                    color: loopActive.value ? "#e9fbe9" : "#d0d0d0"
                    font.pixelSize: 17
                }
            }
            Stepper { anchors.fill: parent; step: win.stepLoop }
        }
    }

    // Remaining time; red from Traktor's own end-of-track warning, 30 s before.
    Component {
        id: timeElement
        Label {
            height: 21
            verticalAlignment: Text.AlignVCenter
            text: isLoaded.value ? "-" + win.timeText(win.remaining) : "—"
            color: !isLoaded.value ? "#5c5c5c" : win.remaining < 30 ? "#ff4b4b" : win.textColor
            font.pixelSize: 17
        }
    }

    // Beats to the next cue.
    Component {
        id: beatsElement
        Label {
            height: 15
            verticalAlignment: Text.AlignVCenter
            text: isLoaded.value ? win.beatsToCueText() : ""
            color: win.masterColor
            font.pixelSize: 13
            font.bold: true
        }
    }

    // Track artist, under or instead of the title.
    Component {
        id: artistElement
        Label {
            width: parent ? parent.cellWidth : 0
            height: 18
            verticalAlignment: Text.AlignVCenter
            text: isLoaded.value ? (trackArtist.value || "") : ""
            elide: Text.ElideRight
            color: "#b3b3b3"
            font.pixelSize: 12
        }
    }

    // Time played.
    Component {
        id: elapsedElement
        Label {
            height: 21
            verticalAlignment: Text.AlignVCenter
            text: isLoaded.value ? win.timeText(Number(elapsedTime.value) || 0) : "—"
            font.pixelSize: 17
        }
    }

    // Beat counter: the beat the track is on, as phrase.bar.beat.
    Component {
        id: beatCounterElement
        Label {
            height: 15
            verticalAlignment: Text.AlignVCenter
            text: isLoaded.value ? win.beatCounterText() : ""
            font.pixelSize: 13
            font.bold: true
        }
    }

    // SYNC over MASTER, lit as Traktor's own: orange and blue.
    Component {
        id: syncMasterElement
        Column {
            width: 46
            height: 39
            spacing: 3
            Repeater {
                model: [{label: "SYNC", on: Boolean(syncEnabled.value), color: win.syncColor},
                        {label: "MASTER", on: win.isMaster, color: win.masterColor}]
                Rectangle {
                    width: 46
                    height: 18
                    radius: 2
                    color: modelData.on ? Qt.rgba(modelData.color.r, modelData.color.g, modelData.color.b, 0.22)
                         : syncArea.pressed ? "#333333" : "#242424"
                    border.color: modelData.on ? modelData.color : "#333333"
                    Label {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: modelData.on ? modelData.color : "#b3b3b3"
                        font.pixelSize: 9
                        font.bold: true
                        font.letterSpacing: 0.5
                    }
                    MouseArea {
                        id: syncArea
                        anchors.fill: parent
                        onClicked: {
                            if (index === 0) syncEnabled.value = !syncEnabled.value
                            else setAsMaster.value = true
                        }
                    }
                }
            }
        }
    }

    // Hotcues 1-8 in two rows of 4, numbered in their type's colour; empty
    // ones dimmed. They work as Traktor's hotcue buttons (a press jumps or
    // sets, holding on a stopped deck plays); a right click deletes.
    Component {
        id: cuesElement
        Grid {
            id: cueGrid
            width: parent ? parent.cellWidth : 0
            height: 47
            columns: 4
            spacing: 3
            Repeater {
                model: 8
                Rectangle {
                    id: cue
                    readonly property int n: index + 1
                    readonly property bool exists: Boolean(cueExists.value) && Number(cueType.value) !== -1
                    readonly property color typeColor: win.hotcueColors[Number(cueType.value)] || win.hotcueColors[0]
                    readonly property bool lit: exists && Boolean(cueActive.value)

                    AppProperty { id: cueExists; path: win.pathPrefix + "track.cue.hotcues." + cue.n + ".exists" }
                    AppProperty { id: cueType;   path: win.pathPrefix + "track.cue.hotcues." + cue.n + ".type" }
                    AppProperty { id: cueActive; path: win.pathPrefix + "track.cue.hotcues." + cue.n + ".active" }

                    width: (cueGrid.width - (cueGrid.columns - 1) * cueGrid.spacing) / cueGrid.columns
                    height: 22
                    radius: 2
                    color: lit ? Qt.rgba(typeColor.r, typeColor.g, typeColor.b, 0.18)
                         : exists ? "#232323" : "#1e1e1e"
                    border.color: lit ? Qt.rgba(typeColor.r, typeColor.g, typeColor.b, 0.6) : "#2e2e2e"

                    Label {
                        anchors.centerIn: parent
                        text: cue.n
                        color: cue.exists ? cue.typeColor : "#4a4a4a"
                        font.pixelSize: 11
                        font.bold: true
                    }
                    // Held as a controller's hotcue pad is (HoldPropertyAdapter
                    // in Traktor's X1 MK3 mapping): the index while the button
                    // is down, the idle value again when it is let go. Traktor
                    // then does the rest: on a stopped deck a press jumps
                    // there, holding plays from it and letting go goes back.
                    MouseArea {
                        anchors.fill: parent
                        enabled: isLoaded.value
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        property bool holding: false
                        onPressed: {
                            if (mouse.button === Qt.RightButton) {
                                if (cue.exists) deleteHotcue.value = index
                                return
                            }
                            win.hotcueDown(index)
                            holding = true
                        }
                        onReleased: release()
                        onCanceled: release()
                        onEnabledChanged: if (!enabled) release()
                        Component.onDestruction: release()
                        function release() {
                            if (!holding) return
                            holding = false
                            win.hotcueUp()
                        }
                    }
                }
            }
        }
    }

    // Both windows take their lane's height (minus a 4 px margin), which comes
    // from the layout and can be as low as Traktor's own 87; PanelBody leaves
    // rows out when they do not fit.
    PanelBody {
        anchors.fill: parent
        anchors.leftMargin: win.settings.panelMargin.left
        anchors.rightMargin: win.settings.panelMargin.left
        layout: win.settings.plan(win.settings.left, width, height).rows
        components: win.components
        // Empty, not dashes, with no track loaded.
        visible: Boolean(isLoaded.value)
        lineColor: win.lineColor
    }

    // The stems panel, right of this one, or at the lane's left end while
    // this one is hidden (the placing script puts it there): per stem its
    // icon, a click on which mutes it, then the sections turned on in the
    // settings window: volume, filter and FX send, each a knob, the last two
    // with the dot that turns them on. As wide as what it shows. It stands
    // in for Traktor's own stem controls, which the placing script hides.
    // Only on a Stem deck with a track: a track without stems loads into a
    // Track deck.
    readonly property bool isStemDeck: Number(deckType.value) === 2
    readonly property bool stemsHidden: !settings.showStems || !isStemDeck || !isLoaded.value
    // Traktor's colour palette for color_id 1-16 (Screens/Defines/Colors.qml).
    readonly property var stemPalette: ["#808080", "#ff0000", "#ff1010", "#ff7800", "#ffb800", "#ffff00", "#90ff00",
                                        "#28ff28", "#00d080", "#00b8e8", "#0078ff", "#0048ff", "#8000ff",
                                        "#a000c8", "#f000c8", "#ff0078", "#f80840"]
    Window {
        id: stemsWin
        transientParent: null
        title: "TraktorLanePanel " + win.deckLetter + " stems" + (win.stemsHidden ? " hidden" : "")
               + (browserFullScreen.value ? " browser" : "")
        flags: win.flags
        readonly property int sections: (win.settings.stemVolume ? 1 : 0) + (win.settings.stemFilter ? 1 : 0)
                                        + (win.settings.stemFx ? 1 : 0)
        width: 4 + 3 + 4 + 16 + 4 + (win.settings.stemVolume ? 24 : 0)
               + (win.settings.stemFilter ? 32 : 0) + (win.settings.stemFx ? 32 : 0)
        height: 212
        color: win.color
        visible: true

        Column {
            x: 2
            y: 1
            width: parent.width - 4
            spacing: 1
            Repeater {
                model: 4
                Rectangle {
                    id: stemRow
                    readonly property int n: index + 1
                    readonly property string path: win.pathPrefix + "stems." + n + "."
                    readonly property bool isMuted: Boolean(muted.value)
                    readonly property color stemColor: win.stemPalette[Number(colorId.value)] || win.stemPalette[0]
                    width: parent.width
                    height: Math.floor((stemsWin.height - 2 - 3) / 4)
                    radius: 2
                    color: "#232323"

                    AppProperty { id: muted;     path: stemRow.path + "muted" }
                    AppProperty { id: volume;    path: stemRow.path + "volume" }
                    // The filter superknob: 0.5 off, LPF to the left, HPF to the right.
                    // "filter" itself does not move it; Traktor's own mappings use this.
                    AppProperty { id: filter;    path: stemRow.path + "filter_value" }
                    AppProperty { id: filterOn;  path: stemRow.path + "filter_on" }
                    AppProperty { id: fxSend;    path: stemRow.path + "fx_send" }
                    AppProperty { id: fxSendOn;  path: stemRow.path + "fx_send_on" }
                    AppProperty { id: colorId;   path: stemRow.path + "color_id" }

                    Rectangle {
                        x: 2
                        anchors.verticalCenter: parent.verticalCenter
                        width: 3
                        height: Math.max(8, parent.height - 6)
                        radius: 1
                        color: stemRow.stemColor
                        opacity: stemRow.isMuted ? 0.35 : 1
                    }
                    StemIcon {
                        x: 9
                        anchors.verticalCenter: parent.verticalCenter
                        stem: stemRow.n
                        color: !isLoaded.value ? "#4a4a4a" : stemRow.isMuted ? "#5a5a5a" : "#d8d8d8"
                    }
                    MouseArea {
                        x: 0
                        width: 29
                        height: parent.height
                        enabled: isLoaded.value
                        onClicked: muted.value = !stemRow.isMuted
                    }

                    Row {
                        x: 31
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        opacity: isLoaded.value ? 1 : 0.4
                        StemKnob {
                            visible: win.settings.stemVolume
                            value: Number(volume.value) || 0
                            resetValue: 1
                            onMoved: volume.value = value
                        }
                        StemKnob {
                            visible: win.settings.stemFilter
                            bipolar: true
                            hasDot: true
                            value: isFinite(Number(filter.value)) ? Number(filter.value) : 0.5
                            resetValue: 0.5
                            on: Boolean(filterOn.value)
                            arcColor: win.masterColor
                            onMoved: filter.value = value
                            onToggled: filterOn.value = !on
                        }
                        StemKnob {
                            visible: win.settings.stemFx
                            hasDot: true
                            value: Number(fxSend.value) || 0
                            resetValue: 0
                            on: Boolean(fxSendOn.value)
                            arcColor: win.syncColor
                            onMoved: fxSend.value = value
                            onToggled: fxSendOn.value = !on
                        }
                    }
                }
            }
        }
    }

    // The right end of the lane. Its own top-level window, like this one;
    // the placing script puts it against the lane's end, whatever its width.
    Window {
        id: info
        transientParent: null
        title: "TraktorLanePanel " + win.deckLetter + " info" + (win.infoHidden ? " hidden" : "")
               + (browserFullScreen.value ? " browser" : "")
        flags: win.flags
        width: win.settings.rightWidth
        height: 212
        color: win.color
        visible: true

        PanelBody {
            anchors.fill: parent
            anchors.leftMargin: win.settings.panelMargin.right
            anchors.rightMargin: win.settings.panelMargin.right
            layout: win.settings.plan(win.settings.right, width, height).rows
            components: win.components
            visible: Boolean(isLoaded.value)
            lineColor: win.lineColor
        }
    }
}
