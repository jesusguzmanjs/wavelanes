import QtQuick 2.15

// A small knob for a stem: an arc over 270°, from the start (or from the
// middle, bipolar, for the filter), and optionally the dot that turns its
// section on or off, as on Traktor's own stem controls. Drag up or down, or
// the wheel, to turn it; a double click puts it back to resetValue; a click
// on the dot toggles it. The value is 0-1; changes go out by moved(value)
// and toggled(), for the owner to write to Traktor.
Item {
    id: knob
    property real value: 0
    property bool bipolar: false
    property real resetValue: 0
    property bool hasDot: false
    property bool on: true
    property color arcColor: "#e6e6e6"
    property color trackColor: "#3a3a3a"
    property color dotColor: arcColor
    signal moved(real value)
    signal toggled

    readonly property int dial: 18
    width: dial + (hasDot ? 8 : 0)
    height: dial

    onValueChanged: arc.requestPaint()
    onOnChanged: arc.requestPaint()
    onArcColorChanged: arc.requestPaint()

    Canvas {
        id: arc
        width: knob.dial
        height: knob.dial
        onPaint: {
            var c = getContext("2d")
            c.reset()
            var r = width / 2 - 2, cx = width / 2, cy = height / 2
            var start = 0.75 * Math.PI, span = 1.5 * Math.PI
            var v = Math.max(0, Math.min(1, knob.value))
            c.lineWidth = 2
            c.lineCap = "round"
            c.strokeStyle = knob.trackColor
            c.beginPath()
            c.arc(cx, cy, r, start, start + span)
            c.stroke()
            var from = knob.bipolar ? start + span / 2 : start
            var to = start + span * v
            if (Math.abs(to - from) > 0.01) {
                c.strokeStyle = knob.on ? knob.arcColor : "#6a6a6a"
                c.beginPath()
                c.arc(cx, cy, r, Math.min(from, to), Math.max(from, to))
                c.stroke()
            }
        }
    }

    Rectangle {
        visible: knob.hasDot
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 4
        width: 5
        height: 5
        radius: 2.5
        color: knob.on ? knob.dotColor : "#4a4a4a"
    }

    MouseArea {
        anchors.fill: arc
        property real lastY: 0
        preventStealing: true
        onPressed: lastY = mouse.y
        onPositionChanged: {
            var v = Math.max(0, Math.min(1, knob.value + (lastY - mouse.y) / 100))
            lastY = mouse.y
            knob.moved(v)
        }
        onDoubleClicked: knob.moved(knob.resetValue)
        onWheel: knob.moved(Math.max(0, Math.min(1, knob.value + (wheel.angleDelta.y > 0 ? 0.05 : -0.05))))
    }
    MouseArea {
        visible: knob.hasDot
        anchors.left: arc.right
        anchors.right: parent.right
        height: parent.height
        onClicked: knob.toggled()
    }
}
