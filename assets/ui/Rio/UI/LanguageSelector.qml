import QtQuick
import QtQuick.Controls

Slider {
  property string language: "zh"
 property bool zh: language === "zh"
 signal languageRequested(string value)
 id: languageSlider
  width: 76; height: 26; padding: 2; from: 0; to: 1; stepSize: 1; snapMode: Slider.SnapAlways
  hoverEnabled: true; value: languageSlider.zh ? 1 : 0
  Accessible.name: (zh ? "语言" : "Language")
  onMoved: languageRequested(value>=0.5 ? "zh" : "en")
  background: Item {
   SoftShadow { anchors.fill: parent; cornerRadius: 6 }
   Rectangle { id: languageTrack; anchors.fill: parent; radius: 6; color: languageSlider.hovered ? "#333b40" : "#272d30"; Behavior on color { ColorAnimation { duration: 100 } }
    gradient: Gradient {
     GradientStop { position: 0; color: Qt.darker(languageTrack.color,1.6) }
     GradientStop { position: 0.42; color: languageTrack.color }
     GradientStop { position: 1; color: Qt.lighter(languageTrack.color,1.08) }
    }
    Rectangle { x: 1; y: 1; width: parent.width-2; height: parent.height-2; radius: 5; color: "transparent"; border.width: 1; border.color: "#33000000" }
   }
  }
  handle: Item {
   z: 2
   x: languageSlider.leftPadding+languageSlider.visualPosition*(languageSlider.availableWidth-width)
   y: languageSlider.topPadding; width: 35; height: 22
   Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
   SoftShadow { anchors.fill: parent; cornerRadius: 4 }
   Rectangle { anchors.fill: parent; radius: 4; color: languageSlider.pressed ? "#fff07e" : languageSlider.hovered ? "#ffea61" : "#ffdf32" }
  }
  Row { anchors.fill: parent; z: 3
   Repeater { model: ["EN","CN"]; delegate: RioText { required property string modelData; required property int index; width: 38; height: 26; text: modelData; color: index===Math.round(languageSlider.value) ? "#17210f" : "#a7eb52"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter } }
  }
 }
