import QtQuick 2.12
import QtQuick.Window 2.12

// Shown by the lane panel launcher when LanePanel.qml fails to load: Traktor
// keeps no log of QML errors, so this is the only place to read them. The
// title must not start with "TraktorLanePanel ", or the placing script would
// take it for a panel.
Window {
    property string message
    title: "Lane panel error"
    flags: Qt.Tool
    width: 720
    height: 240
    color: "#3a1010"
    visible: true

    Text {
        anchors.fill: parent
        anchors.margins: 10
        text: message
        color: "#ffffff"
        font.pixelSize: 13
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }
}
