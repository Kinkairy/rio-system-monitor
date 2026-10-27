import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
  popupType: Popup.Item; parent: Overlay.overlay; x: (parent ? (parent.width-width)/2 : 0); y: (parent ? (parent.height-height)/2 : 0)
  width: 280; height: 356; modal: true; focus: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  Overlay.modal: Rectangle { color: "#99080a0c" }
 }
