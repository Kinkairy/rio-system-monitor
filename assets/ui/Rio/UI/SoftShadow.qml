import QtQuick
import QtQuick.Controls

Item {
  property bool pressed: false
  property real cornerRadius: 8
  Rectangle { x: -1; y: 2; width: parent.width+2; height: parent.height+2; radius: parent.cornerRadius+1; color: "black"; opacity: parent.pressed ? 0.06 : 0.12 }
  Rectangle { y: 2; width: parent.width; height: parent.height; radius: parent.cornerRadius; color: "black"; opacity: parent.pressed ? 0.08 : 0.18 }
 }
