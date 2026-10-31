import QtQuick 2.15

// The icon of stem 1-4, in Traktor's order: drums, bass, other, vocals.
// Drawn here, since Traktor's own are inside its executable.
Canvas {
    id: icon
    property int stem: 1
    property color color: "#cfcfcf"
    width: 16
    height: 16
    onColorChanged: requestPaint()
    onStemChanged: requestPaint()

    onPaint: {
        var c = getContext("2d")
        c.reset()
        c.strokeStyle = icon.color
        c.fillStyle = icon.color
        c.lineWidth = 1.5
        if (stem === 1) {
            // A drum: the top as an ellipse, the shell under it.
            c.beginPath()
            c.ellipse(2, 3, 12, 5)
            c.stroke()
            c.beginPath()
            c.moveTo(2, 5.5); c.lineTo(2, 12)
            c.moveTo(14, 5.5); c.lineTo(14, 12)
            c.stroke()
            c.beginPath()
            c.ellipse(2, 9.5, 12, 5)
            c.stroke()
        } else if (stem === 2) {
            // A speaker: a box with a cone.
            c.strokeRect(2.5, 2.5, 11, 11)
            c.beginPath()
            c.arc(8, 8, 3.2, 0, 2 * Math.PI)
            c.stroke()
            c.beginPath()
            c.arc(8, 8, 1, 0, 2 * Math.PI)
            c.fill()
        } else if (stem === 3) {
            // Bars, as a level.
            var bars = [6, 10, 13, 9, 5]
            for (var i = 0; i < bars.length; i++)
                c.fillRect(1.5 + i * 2.8, 8 - bars[i] / 2, 1.6, bars[i])
        } else {
            // A microphone.
            c.beginPath()
            c.moveTo(6, 4); c.arc(8, 4, 2, Math.PI, 0); c.lineTo(10, 8.5)
            c.arc(8, 8.5, 2, 0, Math.PI); c.closePath()
            c.fill()
            c.beginPath()
            c.arc(8, 8, 4, 0, Math.PI)
            c.moveTo(8, 12); c.lineTo(8, 14.5)
            c.moveTo(5.5, 14.5); c.lineTo(10.5, 14.5)
            c.stroke()
        }
    }
}
