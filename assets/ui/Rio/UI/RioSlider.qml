import QtQuick
import QtQuick.Controls

Slider {
 id: control
 property bool fillTrack: false
 property bool hueTrack: false
 property color thumbColor: "#a7eb52"
 hoverEnabled: true
 opacity: enabled ? 1 : 0.35
 implicitHeight: 32
 background: Rectangle {
  x: control.leftPadding; y: control.topPadding+control.availableHeight/2-height/2
  width: control.availableWidth; height: control.hueTrack ? 12 : 4; radius: height/2
  color: control.hovered ? "#607451" : "#343d40"
  gradient: control.hueTrack ? hueGradient : null
  Gradient { id: hueGradient; orientation: Gradient.Horizontal
   GradientStop { position: 0; color: "#ff0000" } GradientStop { position: 1/6; color: "#ffff00" }
   GradientStop { position: 2/6; color: "#00ff00" } GradientStop { position: 3/6; color: "#00ffff" }
   GradientStop { position: 4/6; color: "#0000ff" } GradientStop { position: 5/6; color: "#ff00ff" }
   GradientStop { position: 1; color: "#ff0000" }
  }
  Rectangle { visible: control.fillTrack && !control.hueTrack; width: control.visualPosition*parent.width; height: parent.height; radius: parent.radius; color: "#a7eb52" }
 }
 handle: Rectangle {
  x: control.leftPadding+control.visualPosition*(control.availableWidth-width)
  y: control.topPadding+control.availableHeight/2-height/2
  width: control.hueTrack ? 20 : 18; height: width; radius: width/2
  color: control.pressed || control.hovered ? "#d1ff9b" : control.thumbColor
  border.width: control.hueTrack ? 3 : control.hovered ? 2 : 0
  border.color: "#ecffd7"
 }
}
