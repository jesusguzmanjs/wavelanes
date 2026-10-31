import QtQuick 2.15
import QtQuick.Window 2.15

// The settings button, over Traktor's header just after its logo. Opens and
// closes the settings window. Placed by the same script as the lane panels,
// which finds it by its title.
Window {
    id: button
    property PanelSettings settings
    title: "WaveLanes button"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    width: 22
    height: 22
    color: "#1a1a1a"
    visible: true

    Rectangle {
        anchors.fill: parent
        radius: 3
        color: area.pressed ? "#333333" : area.containsMouse || button.settings.configOpen ? "#2a2a2a" : "#1a1a1a"
        border.color: button.settings.configOpen ? "#2ba0e0" : "#333333"
    }

    // Three sliders.
    Repeater {
        model: [{y: 6, knob: 11}, {y: 10, knob: 5}, {y: 14, knob: 13}]
        Item {
            x: 5
            y: modelData.y
            width: 12
            height: 3
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                height: 1
                color: "#b3b3b3"
            }
            Rectangle {
                x: modelData.knob - 1.5 - parent.x
                width: 3
                height: 3
                radius: 1.5
                color: button.settings.configOpen ? "#2ba0e0" : "#e6e6e6"
            }
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        onClicked: button.settings.configOpen = !button.settings.configOpen
    }
}
