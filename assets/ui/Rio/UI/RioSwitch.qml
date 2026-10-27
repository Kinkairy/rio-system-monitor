import QtQuick
import QtQuick.Controls

Switch {
  id: sw
  hoverEnabled: true
  implicitWidth: 42; implicitHeight: 24
  indicator: Rectangle {
   id: switchTrack
   width: 42; height: 24; radius: 12; color: !sw.enabled ? "#343a3e" : sw.pressed ? "#d1ff9b" : sw.hovered ? "#c4ff7b" : sw.checked ? "#a7eb52" : "#343a3e"; border.width: sw.enabled && (sw.hovered || sw.activeFocus) ? 1 : 0; border.color: "#d1ff9b"
   gradient: Gradient {
    GradientStop { position: 0; color: Qt.darker(switchTrack.color,1.2) }
    GradientStop { position: 0.38; color: switchTrack.color }
    GradientStop { position: 1; color: Qt.lighter(switchTrack.color,1.04) }
   }
   Behavior on color { ColorAnimation { duration: 130 } }
   Rectangle { x: 1; y: 1; width: parent.width-2; height: parent.height-2; radius: 11; color: "transparent"; border.width: 1; border.color: "#24000000" }
   Rectangle { width: 18; height: 18; y: 5; x: switchThumb.x; radius: 9; color: "#000000"; opacity: sw.enabled ? 0.22 : 0.1 }
   Rectangle { id: switchThumb; width: 18; height: 18; y: 3; x: sw.checked ? 21 : 3; radius: 9; color: !sw.enabled ? "#7b8489" : sw.checked || sw.hovered || sw.pressed ? "#18200e" : "#a4acb0"; Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } } }
  }
 }
