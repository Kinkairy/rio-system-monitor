import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
  property bool highlighted: false
  SoftShadow { objectName: "fieldShadow"; anchors.fill: parent; cornerRadius: 7 }
  Rectangle { anchors.fill: parent; color: "#11171b"; radius: 7; border.color: parent.highlighted ? "#a7eb52" : "#354047"; border.width: 1 }
 }
