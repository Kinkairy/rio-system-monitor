import QtQuick
import QtQuick.Controls

Slider {
 id: control
 property bool fillTrack: false
 property bool hueTrack: false
 property color thumbColor: "#a7eb52"
 // A choice among a few positions, not an amount: nodes on a thin line, no fill.
 property int stops: 0
 readonly property bool discrete: stops>1
 function stopX(index){return leftPadding+6+(discrete ? index/(stops-1) : 0)*(availableWidth-12)}
 hoverEnabled: true
 opacity: enabled ? 1 : 0.35
 implicitHeight: 32
 background: Rectangle {
  x: control.discrete ? control.stopX(0) : control.leftPadding; y: control.topPadding+control.availableHeight/2-height/2
  width: control.discrete ? control.stopX(control.stops-1)-control.stopX(0) : control.availableWidth; height: control.discrete ? 2 : control.hueTrack ? 12 : 4; radius: height/2
  color: control.discrete ? "#3a4448" : control.hovered ? "#607451" : "#343d40"
  gradient: control.hueTrack ? hueGradient : null
  Gradient { id: hueGradient; orientation: Gradient.Horizontal
   GradientStop { position: 0; color: "#ff0000" } GradientStop { position: 1/6; color: "#ffff00" }
   GradientStop { position: 2/6; color: "#00ff00" } GradientStop { position: 3/6; color: "#00ffff" }
   GradientStop { position: 4/6; color: "#0000ff" } GradientStop { position: 5/6; color: "#ff00ff" }
   GradientStop { position: 1; color: "#ff0000" }
  }
  Rectangle { visible: control.fillTrack && !control.hueTrack && !control.discrete; width: control.visualPosition*parent.width; height: parent.height; radius: parent.radius; color: "#a7eb52" }
  Repeater { model: control.discrete ? control.stops : 0
   Rectangle { required property int index; objectName: "sliderStop"+index; width: 12; height: 12; radius: 6; y: (parent.height-height)/2; x: control.stopX(index)-parent.x-width/2; color: "#1a2024"; border.width: 2; border.color: "#4f5b60" }
  }
 }
 handle: Rectangle {
  x: control.discrete ? control.stopX(control.visualPosition*(control.stops-1))-width/2 : control.leftPadding+control.visualPosition*(control.availableWidth-width)
  y: control.topPadding+control.availableHeight/2-height/2
  width: control.discrete ? 12 : control.hueTrack ? 20 : 18; height: width; radius: width/2
  // A selected node keeps its ring; only the centre lights up.
  color: control.discrete ? "#1a2024" : control.pressed || control.hovered ? "#d1ff9b" : control.thumbColor
  border.width: control.discrete ? 2 : control.hueTrack ? 3 : control.hovered ? 2 : 0
  border.color: control.discrete ? (control.hovered || control.pressed ? "#8a979c" : "#4f5b60") : "#ecffd7"
  Rectangle { visible: control.discrete; anchors.centerIn: parent; width: 6; height: 6; radius: 3; color: control.pressed || control.hovered ? "#d1ff9b" : control.thumbColor }
  Behavior on x { enabled: control.discrete && !control.pressed; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
 }
}
