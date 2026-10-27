import QtQuick
import QtQuick.Controls

ComboBox {
 id: control
 implicitHeight: 36
 background: Rectangle { color: "#11171b"; radius: 7; border.color: "#354047" }
 contentItem: RioText { text: control.displayText; color: "#e5e8e9"; verticalAlignment: Text.AlignVCenter; leftPadding: 10; rightPadding: 24; elide: Text.ElideRight; font.pixelSize: 12 }
 indicator: Item { x: control.width-22; y: 13; width: 12; height: 8
  Rectangle { x: 1; y: 2; width: 6; height: 1.5; rotation: 45; color: "#a7eb52"; antialiasing: true }
  Rectangle { x: 5; y: 2; width: 6; height: 1.5; rotation: -45; color: "#a7eb52"; antialiasing: true }
 }
 delegate: ItemDelegate { width: control.width; contentItem: RioText { text: control.textRole ? modelData[control.textRole] : modelData; color: "#e5e8e9"; elide: Text.ElideRight } background: Rectangle { color: highlighted ? "#354331" : "#1a2024" } }
 popup: Popup { y: control.height; width: control.width; padding: 2; background: Rectangle { color: "#1a2024"; radius: 6; border.color: "#354047" } contentItem: ListView { implicitHeight: Math.min(contentHeight,160); clip: true; model: control.popup.visible ? control.delegateModel : null; currentIndex: control.highlightedIndex } }
}
