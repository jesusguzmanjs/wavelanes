import QtQuick 2.15

// All the settings of the settings window (ConfigWindow.qml), kept in
// settings.json, in the user's data folder (ui_settings.py): read on start and written a moment
// after each change. What the panels show applies at once.
//
// The layout settings (hideDecks, hideBrowser, lanes, laneHeight, waveBuffer)
// are patched
// into Traktor's copy by the launcher, with Traktor closed, the next time it
// opens Traktor; it records what it applied in "applied" (ui_settings.py).
// One that differs from it waits for a restart, and can be put back.
// QML reads and writes local files only with QML_XHR_ALLOW_FILE_READ and
// QML_XHR_ALLOW_FILE_WRITE set to 1 in Traktor's environment, which the
// launcher does; without them the defaults are used and nothing is kept.
QtObject {
    id: s
    property url file

    // What each panel shows: its three rows, each two slots holding an element's
    // name or "" (see elementNames). An element takes one slot; title and
    // cues (wholeRow) take a row, in its first slot. An element is in one
    // slot at most.
    property var left: [["title", ""], ["bpmPitch", "bpmButtons"], ["key", "loop"]]
    property var right: [["time", "beats"], ["cues", ""], ["", ""]]
    // Panel widths, from minWidth to maxWidth in steps of 10. minWidth is
    // the same for every panel: wide enough for any two elements side by side,
    // each in half the row (the widest, the remaining time, is 53 px). The placing script
    // places each panel with its window's width.
    property int leftWidth: 130
    property int rightWidth: 130
    readonly property int minWidth: 130
    readonly property int maxWidth: 300
    // Left panel shown.
    property bool showLeft: true
    // Right panel shown.
    property bool showInfo: true
    // Stems panel (next to the left one, or on its own), and its sections.
    property bool showStems: false
    property bool stemVolume: true
    property bool stemFilter: true
    property bool stemFx: true
    // MIDI Controls > Button N in the Controller Manager hides the right panels.
    property int midiButton: 4
    // Layout: applied by the launcher on the next start (see above).
    property bool hideDecks: true
    property bool hideBrowser: false
    property int lanes: 3
    property int laneHeight: 216
    property int waveBuffer: 22
    // What the launcher last applied, {hideDecks, lanes, laneHeight,
    // waveBuffer}, or null; written by it, only kept here.
    property var applied: null
    readonly property var layoutKeys: ["hideDecks", "hideBrowser", "lanes", "laneHeight", "waveBuffer"]

    // Not kept.
    property bool configOpen: false
    property bool loaded: false
    property string saveError: ""

    readonly property var keys: ["left", "right", "leftWidth", "rightWidth", "showLeft", "showInfo",
                                 "showStems", "stemVolume", "stemFilter", "stemFx", "midiButton",
                                 "hideDecks", "hideBrowser", "lanes", "laneHeight", "waveBuffer", "applied"]

    // The elements, in the order the settings window lists them, and their
    // names there. bpm and bpmPitch are the same element, with and without
    // the pitch over it. The panels make them (LanePanel.qml).
    readonly property var elementNames: ["title", "artist", "bpmPitch", "bpm", "bpmButtons", "syncMaster", "key", "loop",
                                         "time", "elapsed", "beats", "beatCounter", "cues"]
    readonly property var elementLabels: ({
        "": "None", title: "Title", bpmPitch: "BPM & Pitch", bpm: "BPM",
        bpmButtons: "x2 & /2", key: "Key", loop: "Loop", time: "Remaining Time",
        beats: "Beats to Cue", cues: "Hotcues", artist: "Artist", elapsed: "Elapsed Time",
        beatCounter: "Beats", syncMaster: "Sync & Master"
    })
    readonly property var wholeRow: ["title", "artist", "cues"]

    // What the panels need of each element (the elements themselves are in
    // LanePanel.qml): width, the room it needs beside another in a row, 0 for
    // one that takes the whole row; height, its own; priority, on a lane too
    // low for every row the rows with the lowest go first; room, what a row
    // with it needs to spare (the hotcues are left out under 100 px). The
    // widths are the widest each can get, measured in Traktor's font: BPM
    // "188.9" (pitch "-100.00%" over it), key "G#m" (or "12m") under "+12",
    // loop "1/32" under LOOP, time "-12:34", beats "- 88.4.4". Values are
    // 17 px, beats 13 px, labels (pitch, semitone shift, LOOP) small over
    // their value.
    readonly property var elementSpecs: ({
        title:      {width: 0,  height: 20, priority: 0},
        artist:     {width: 0,  height: 18, priority: 0},
        bpmPitch:   {width: 51, height: 35, priority: 2},
        bpm:        {width: 51, height: 35, priority: 2},
        bpmButtons: {width: 26, height: 39, priority: 2},
        syncMaster: {width: 46, height: 39, priority: 2},
        key:        {width: 41, height: 35, priority: 2},
        loop:       {width: 50, height: 35, priority: 2},
        time:       {width: 53, height: 21, priority: 2},
        elapsed:    {width: 46, height: 21, priority: 2},
        beats:      {width: 49, height: 15, priority: 2},
        beatCounter: {width: 49, height: 15, priority: 2},
        cues:       {width: 0,  height: 47, priority: 1, room: 18}
    })
    readonly property int minRowHeight: 32
    readonly property int sideGap: 8
    readonly property int lineRoom: 7
    // Each panel's content is its width less these margins, each side.
    readonly property var panelMargin: ({left: 8, right: 5})
    // The height of lane A's panels, as the placing script set it; the
    // settings window shows what does not fit in it. Not kept.
    property int panelHeight: 0

    // How a panel of width x height lays out its rows (PanelBody.qml draws it):
    // {rows, dropped}. rows: [{names, side, top, height, lineBelow}] for the
    // rows shown; dropped: the names of the elements left out for room.
    //
    // Two elements share a row side by side, each at the start of its half
    // (minWidth makes room for any two); one alone is centred. Each row is as tall as its content, at least
    // minRowHeight, and the room left over is shared out equally; with rows
    // of the same height that centres the middle one in the panel. A line
    // separates the rows when there is lineRoom to spare in each. On a panel
    // too low for every row and its room, rows are left out, the lowest
    // priority first (the first of equals). Unknown names, and "", are left
    // out; a row with a whole-row element holds only that one.
    function plan(rows, width, height) {
        var spec = elementSpecs
        var list = []
        rows.forEach(function (row) {
            var names = row.filter(function (n) { return spec[n] !== undefined })
            var whole = names.filter(function (n) { return spec[n].width === 0 })
            if (whole.length > 0) names = [whole[0]]
            if (names.length === 0) return
            var side = names.length === 2
            var heights = names.map(function (n) { return spec[n].height })
            var content = side ? Math.max.apply(null, heights) : heights.reduce(function (a, b) { return a + b }, 0)
            list.push({names: names, side: side,
                       natural: Math.max(minRowHeight, content),
                       priority: Math.max.apply(null, names.map(function (n) { return spec[n].priority })),
                       room: Math.max.apply(null, names.map(function (n) { return spec[n].room || 0 }))})
        })
        function total() { return list.reduce(function (a, r) { return a + r.natural }, 0) }
        function room() { return list.reduce(function (a, r) { return a + r.room }, 0) }
        var dropped = []
        while (list.length > 0 && total() + room() > height) {
            let low = 0
            for (let i = 1; i < list.length; i++)
                if (list[i].priority < list[low].priority) low = i
            dropped = dropped.concat(list[low].names)
            list.splice(low, 1)
        }
        var extra = list.length > 0 ? (height - total()) / list.length : 0
        var y = 0
        list.forEach(function (r, i) {
            r.top = Math.round(y)
            y += r.natural + extra
            r.height = Math.round(y) - r.top
            r.lineBelow = i < list.length - 1 && extra >= lineRoom
        })
        return {rows: list, dropped: dropped}
    }

    function widthKey(panel) { return panel === "left" ? "leftWidth" : "rightWidth" }

    // A panel's width as the window sets it, within minWidth and maxWidth.
    function setPanelWidth(panel, width) {
        s[widthKey(panel)] = Math.max(minWidth, Math.min(maxWidth, width))
    }

    // The plan of a panel ("left" or "right") as it is now in lane A.
    function panelPlan(panel) {
        var width = (panel === "left" ? leftWidth : rightWidth) - 2 * panelMargin[panel]
        return plan(s[panel], width, panelHeight)
    }

    function sameElement(a, b) {
        function base(n) { return n === "bpmPitch" ? "bpm" : n }
        return a !== "" && base(a) === base(b)
    }

    // Where an element is: {panel, row, slot}, or null.
    function find(name) {
        var found = null
        ;["left", "right"].forEach(function (panel) {
            s[panel].forEach(function (row, r) {
                row.forEach(function (n, slot) {
                    if (found === null && sameElement(n, name)) found = {panel: panel, row: r, slot: slot}
                })
            })
        })
        return found
    }

    // Put an element ("" for none) in a slot. One already elsewhere swaps
    // places with what the slot held. A row with a whole-row element keeps
    // only that one, in its first slot.
    function place(panel, row, slot, name) {
        var p = {left: JSON.parse(JSON.stringify(left)), right: JSON.parse(JSON.stringify(right))}
        var old = p[panel][row][slot]
        var from = name === "" ? null : find(name)
        if (from !== null) p[from.panel][from.row][from.slot] = old
        p[panel][row][slot] = name
        ;["left", "right"].forEach(function (k) {
            p[k] = p[k].map(function (r) {
                var whole = r.filter(function (n) { return wholeRow.indexOf(n) >= 0 })
                return whole.length > 0 ? [whole[0], ""] : r
            })
        })
        left = p.left
        right = p.right
    }

    // A panel as saved, if it has the shape of one.
    function validPanel(v, rows) {
        return Array.isArray(v) && v.length === rows && v.every(function (r) {
            return Array.isArray(r) && r.length === 2 && r.every(function (n) {
                return n === "" || elementNames.indexOf(n) >= 0
            })
        })
    }

    function values() {
        var d = {}
        keys.forEach(function (k) { d[k] = s[k] })
        return d
    }

    function load() {
        var x = new XMLHttpRequest()
        x.onreadystatechange = function () {
            if (x.readyState !== XMLHttpRequest.DONE) return
            try {
                const d = x.responseText ? JSON.parse(x.responseText) : {}
                if (!validPanel(d.left, 3)) delete d.left
                if (!validPanel(d.right, 3)) delete d.right
                ;["leftWidth", "rightWidth"].forEach(function (k) {
                    if (typeof d[k] === "number") d[k] = Math.max(minWidth, Math.min(maxWidth, Math.round(d[k])))
                })
                keys.forEach(function (k) {
                    if (typeof d[k] === typeof s[k]) s[k] = d[k]
                })
            } catch (e) {
                console.log("[WaveLanes] " + file + ": " + e)
            }
            loaded = true
        }
        x.open("GET", file)
        x.send()
    }

    // A layout setting that differs from what the launcher applied.
    function waiting(key) {
        return applied !== null && applied[key] !== undefined && applied[key] !== s[key]
    }

    readonly property bool restartPending: layoutKeys.some(function (k) { return waiting(k) })

    // Back to what is applied.
    function discardLayout() {
        if (applied === null) return
        layoutKeys.forEach(function (k) {
            if (applied[k] !== undefined) s[k] = applied[k]
        })
    }

    // Written, then read back: a local PUT reports no error of its own.
    function save() {
        var text = JSON.stringify(values(), null, 2) + "\n"
        var put = new XMLHttpRequest()
        put.onreadystatechange = function () {
            if (put.readyState !== XMLHttpRequest.DONE) return
            var get = new XMLHttpRequest()
            get.onreadystatechange = function () {
                if (get.readyState !== XMLHttpRequest.DONE) return
                saveError = get.responseText === text ? "" : "Could not save to " + file
            }
            get.open("GET", file)
            get.send()
        }
        put.open("PUT", file)
        put.send(text)
    }

    property Timer saveTimer: Timer {
        interval: 300
        onTriggered: s.save()
    }

    function changed() {
        if (loaded) saveTimer.restart()
    }

    onLeftChanged: changed()
    onRightChanged: changed()
    onLeftWidthChanged: changed()
    onRightWidthChanged: changed()
    onShowLeftChanged: changed()
    onShowInfoChanged: changed()
    onShowStemsChanged: changed()
    onStemVolumeChanged: changed()
    onStemFilterChanged: changed()
    onStemFxChanged: changed()
    onMidiButtonChanged: changed()
    onHideDecksChanged: changed()
    onHideBrowserChanged: changed()
    onLanesChanged: changed()
    onLaneHeightChanged: changed()
    onWaveBufferChanged: changed()

    Component.onCompleted: load()
}
