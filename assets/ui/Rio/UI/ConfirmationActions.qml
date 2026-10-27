import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
  id: actions
  readonly property bool zh: ApplicationWindow.window ? ApplicationWindow.window.zh : true
  signal accepted()
  signal rejected()
  property string cancelObjectName: ""
  property string okObjectName: ""
  property string okText: (actions.zh ? "确定" : "OK")
  property bool acceptedEnabled: true
  Layout.fillWidth: true; spacing: 8
  ActionButton { objectName: actions.cancelObjectName; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; text: (actions.zh ? "取消" : "Cancel"); onClicked: actions.rejected() }
  ActionButton { objectName: actions.okObjectName; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; text: actions.okText; enabled: actions.acceptedEnabled; fill: "#a7eb52"; ink: "#17210f"; onClicked: actions.accepted() }
 }
