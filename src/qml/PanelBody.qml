import QtQuick 2.15

// The rows of a lane panel, as PanelSettings.plan() laid them out: layout is
// its rows ({names, side, top, height, lineBelow}), and components makes each
// element by name (created in the file that defines it, so it sees that
// file's ids). An element that takes the whole row reads its width from its
// Loader's cellWidth. Two side by side each start at the start of their half
// of the row; one alone is centred.
Item {
    id: body
    property var layout: []
    property var components: ({})
    property color lineColor: "#2b2b2b"
    property int sideGap: 8

    Repeater {
        model: body.layout
        Item {
            id: row
            readonly property var r: modelData
            y: r.top
            width: body.width
            height: r.height

            Rectangle {
                y: parent.height - 1
                width: parent.width
                height: 1
                color: body.lineColor
                visible: row.r.lineBelow
            }

            // Two side by side: each at the start of its half of the row.
            Loader {
                readonly property real cellWidth: (body.width - body.sideGap) / 2
                x: 0
                anchors.verticalCenter: parent.verticalCenter
                active: row.r.side
                sourceComponent: active ? body.components[row.r.names[0]] : null
            }
            Loader {
                readonly property real cellWidth: (body.width - body.sideGap) / 2
                x: (body.width + body.sideGap) / 2
                anchors.verticalCenter: parent.verticalCenter
                active: row.r.side
                sourceComponent: active ? body.components[row.r.names[1]] : null
            }

            Column {
                anchors.centerIn: parent
                visible: !row.r.side
                Repeater {
                    model: row.r.side ? [] : row.r.names
                    Loader {
                        readonly property real cellWidth: body.width
                        anchors.horizontalCenter: parent.horizontalCenter
                        sourceComponent: body.components[modelData]
                    }
                }
            }
        }
    }
}
