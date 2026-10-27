import QtQuick
import QtQuick.Controls

ActionButton {
  property bool zh: true
 id: closeButton
  width: 26; implicitHeight: 30; padding: 0; leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
  text: "×"; fill: "transparent"; hoverFill: "#a7eb52"; ink: hovered || down ? "#17210f" : "#d0d8dd"; showOutline: false; Accessible.name: (zh ? "关闭" : "Close")
  contentItem: Item {
   Item { anchors.fill: parent; anchors.topMargin: 1; anchors.bottomMargin: -1
    Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 2; rotation: 45; color: "#66000000"; antialiasing: true }
    Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 2; rotation: -45; color: "#66000000"; antialiasing: true }
   }
   Rectangle { objectName: "closeStrokeA"; anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 1.5; rotation: 45; color: closeButton.ink; antialiasing: true }
   Rectangle { objectName: "closeStrokeB"; anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 1.5; rotation: -45; color: closeButton.ink; antialiasing: true }
  }
 }
