import QtQuick
import QtQuick.Controls

Button {
  id: b
  property bool fieldStyle: false
  property color fill: fieldStyle ? "#11171b" : "#24282b"
  property color ink: "#e5e8e9"
  property bool showOutline: true
  property color hoverFill: fieldStyle || fill.a === 0 ? "#303b41" : Qt.lighter(fill,1.32)
  leftPadding: fieldStyle ? 12 : 6; rightPadding: fieldStyle ? 12 : 6
  hoverEnabled: true
  opacity: enabled ? 1 : 0.42
  implicitHeight: 38
  background: Item {
   SoftShadow { objectName: "buttonShadow"; anchors.fill: parent; pressed: b.down; visible: b.fill.a>0 || b.hovered || b.down }
   Rectangle { objectName: "buttonSurface"; anchors.fill: parent; radius: 8; color: b.down ? Qt.darker(b.hoverFill,1.18) : b.hovered ? b.hoverFill : b.fill; border.width: b.showOutline && (b.fieldStyle || b.hovered || b.activeFocus) ? 1 : 0; border.color: b.hovered || b.activeFocus ? "#a7eb52" : "#354047"; Behavior on color { ColorAnimation { duration: 100 } } }
  }
  contentItem: RioText { text: b.text; color: b.ink; font: b.font; style: Text.Raised; styleColor: "#66000000"; horizontalAlignment: b.fieldStyle ? Text.AlignLeft : Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
 }
