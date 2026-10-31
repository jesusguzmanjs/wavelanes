import QtQuick 2.15

// Everything WaveLanes adds to Traktor's window, created once by the
// launcher that layout_patch.py injects into a controller mapping: the
// settings, one LanePanel per parallel lane (each with its info panel), the
// settings button over Traktor's header and the settings window. The windows
// are placed by wave_height_mac.js (wave_height.js on Windows), which finds
// them by their title.
Item {
    id: root
    property int lanes: 3
    property url settingsFile
    property var windows: []

    PanelSettings {
        id: settings
        file: root.settingsFile
    }

    function create(name, props) {
        var c = Qt.createComponent(Qt.resolvedUrl(name))
        var o = c.status === Component.Ready ? c.createObject(null, props) : null
        if (o === null) {
            var message = "[WaveLanes] " + (c.errorString() || name + ": createObject failed")
            console.log(message)
            var e = Qt.createComponent(Qt.resolvedUrl("LanePanelError.qml"))
            if (e.status === Component.Ready) o = e.createObject(null, { message: message })
        }
        return o
    }

    Component.onCompleted: {
        var w = []
        for (var i = 0; i < lanes; i++)
            w.push(create("LanePanel.qml", { deckId: i, settings: settings }))
        w.push(create("ConfigButton.qml", { settings: settings }))
        w.push(create("ConfigWindow.qml", { settings: settings }))
        windows = w
    }
}
