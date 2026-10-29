import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Rio.UI 1.0 as Rio

Rio.PanelWindow {
 id: win
 language: bridge.language
 heading: tr("Settings","设置")
 tabs: [tr("Settings","设置"),tr("Extensions","扩展")]
 onTabRequested: function(index){tab=index}
 title: "RIO System Monitor"
 onCloseRequested: bridge.hideWindow()
 onLanguageRequested: function(value){bridge.setLanguage(value)}
 onVisibleChanged: bridge.setPreviewVisible(visible)
 component RioText: Rio.RioText { font.family: win.zh ? "Microsoft YaHei UI" : "Segoe UI" }
 component EnglishText: Rio.EnglishText { }
 component SoftShadow: Rio.SoftShadow {  }
 component ActionButton: Rio.ActionButton {  }
 component ConfirmationActions: Rio.ConfirmationActions { }
 component RefreshButton: Rio.RefreshButton { }
 component CloseButton: Rio.CloseButton {  }
 component DialogPopup: Rio.DialogPopup { }
 component FieldSurface: Rio.FieldSurface { }
 component LanguageSelector: Rio.LanguageSelector {  }
 component RioSwitch: Rio.RioSwitch {  }
  Item { y: 0; width: 420; height: 702
  Item { objectName: "settingsPage"; anchors.fill: parent; visible: win.tab===0
  Item { id: previewClip; objectName: "previewClip"; x: 20; y: 88; width: 170; height: 170; clip: true
   Image { id: screen; anchors.fill: parent; source: "image://monitor/frame?"+bridge.frameId; cache: false; smooth: true; rotation: bridge.rotation; fillMode: Image.PreserveAspectFit }
  }
  RioText { x: 212; y: 119; text: win.tr("Screen rotation","屏幕方向"); color: "#dce3e6"; font.pixelSize: 13 }
  EnglishText { x: 212; y: 147; text: Math.round(rotationSlider.value)+"°"; color: "#a7eb52"; font.pixelSize: 24; font.weight: Font.DemiBold }
  Slider {
   id: rotationSlider; objectName: "rotationSlider"; hoverEnabled: true; x: 204; y: 188; width: 194; height: 32; from: 0; to: 359; stepSize: 1; value: bridge.rotation
   onMoved: bridge.setRotation(Math.round(value))
   background: Rectangle { x: rotationSlider.leftPadding; y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: rotationSlider.availableWidth; height: 4; radius: 2; color: rotationSlider.hovered ? "#607451" : "#343d40" }
   handle: Rectangle { x: rotationSlider.leftPadding+rotationSlider.visualPosition*(rotationSlider.availableWidth-width); y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: 18; height: 18; radius: 9; color: rotationSlider.pressed || rotationSlider.hovered ? "#d1ff9b" : "#a7eb52"; border.width: rotationSlider.hovered ? 2 : 0; border.color: "#ecffd7" }
  }
  RioText { x: 24; y: 280; text: win.tr("Weather","天气"); color: "#dce3e6" }
  ActionButton { x: 20; y: 306; width: 332; text: bridge.cityLabel || win.tr("Select city","选择城市"); onClicked: { cityPopup.open(); searchField.forceActiveFocus() } }
  RefreshButton { objectName: "weatherRefreshButton"; x: 362; y: 306; onClicked: consentPopup.open() }
  RioText { x: 24; y: 365; text: win.tr("Screen content","屏幕内容"); color: "#dce3e6" }
  ActionButton { objectName: "storageButton"; x: 20; y: 390; width: 332; text: bridge.storageBusy ? bridge.storageStatus : bridge.storageError ? win.tr("Operation failed · Choose content again","操作失败 · 请重新选择内容") : bridge.storageStored ? win.tr("Stored content · Manage","屏内内容 · 管理") : win.tr("Video or image · Up to 3.4 MB","视频或图片 · 不超过 3.4 MB"); onClicked: storagePopup.open() }
  RefreshButton { objectName: "restoreDefaultButton"; x: 362; y: 390; enabled: bridge.defaultAvailable && !bridge.storageBusy; Accessible.name: win.tr("Restore default","恢复默认"); ToolTip.visible: hovered; ToolTip.text: win.tr("Restore default","恢复默认"); onClicked: bridge.requestRestoreDefault() }
  RioText { x: 24; y: 445; text: win.tr("Temperature monitoring","温度监控"); color: "#dce3e6" }
  RioText { x: 24; y: 464; width: 318; text: bridge.monitorStatus; color: "#89979f"; font.pixelSize: 10; elide: Text.ElideRight }
  RioSwitch { objectName: "monitorSwitch"; x: 358; y: 439; checked: bridge.monitorChecked; enabled: !bridge.monitorBusy && !bridge.monitorExternal; onToggled: bridge.setMonitorEnabled(checked) }
  RioText { x: 24; y: 490; text: win.tr("Music appreciation","音乐欣赏模式"); color: "#dce3e6" }
  RioSwitch { objectName: "musicSwitch"; x: 358; y: 484; checked: bridge.musicEnabled; onToggled: bridge.setMusicEnabled(checked) }
  RioText { x: 24; y: 535; text: win.tr("Start at login","登录后启动"); color: "#dce3e6" }
  RioSwitch { id: autoSwitch; objectName: "autoSwitch"; x: 358; y: 529; checked: bridge.autostart; onToggled: bridge.setAutostart(checked) }
  }
  // Extensions tab: one card per module, same content the former popup held.
  ColumnLayout { objectName: "extensionsPage"; x: 20; y: 88; width: 380; spacing: 12; visible: win.tab===1
   ExtensionCard {
    id: fangcunCard
    objectName: "fangcunExtension"; heading: win.tr("Fangcun","方寸山")
    ext: fangcunExt; detail: win.extensionDetail(fangcunExt,win.tr("Cultivation mode on","修仙模式已开启"),win.tr("Cultivation mode off","修仙模式未开启"))
    accessory: RioSwitch { objectName: "cultivationSwitch"; checked: fangcunExt.enabled; enabled: !bridge.storageBusy && !fangcunCard.busy; onToggled: { fangcunExt.setEnabled(checked); checked=Qt.binding(function(){return fangcunExt.enabled}) } }
    ActionButton { objectName: "fangcunOpenButton"; width: fangcunCard.actionWidth; height: 34; text: win.tr("Open settings","打开设置"); enabled: fangcunExt.enabled && fangcunExt.state==="ready"; onClicked: fangcunExt.open() }
   }
   ExtensionCard {
    id: blacksharkCard
    objectName: "blacksharkExtension"; heading: win.tr("Fengshen Pro","风神 Pro")
    ext: blacksharkExt; detail: win.extensionDetail(blacksharkExt,win.tr("Cooler control on","散热器控制已开启"),win.tr("Cooler control off","散热器控制未开启"))
    accessory: RioSwitch { objectName: "blacksharkSwitch"; checked: blacksharkExt.enabled; enabled: !blacksharkCard.busy; onToggled: { blacksharkExt.setEnabled(checked); checked=Qt.binding(function(){return blacksharkExt.enabled}) } }
    ActionButton { objectName: "blacksharkOpenButton"; width: blacksharkCard.actionWidth; height: 34; text: win.tr("Open settings","打开设置"); enabled: blacksharkExt.enabled && blacksharkExt.state==="ready"; onClicked: blacksharkExt.open() }
   }
  }
  Rectangle { x: 20; y: 630; width: 380; height: 1; color: "#292f32" }
  Rectangle {
   objectName: "updateConnectionLamp"; x: 24; y: 662; width: 8; height: 8; radius: 4; antialiasing: true
   color: bridge.updateConnection==="connected" ? "#a7eb52" : bridge.updateConnection==="failed" ? "#eb7070" : "#68767d"
   HoverHandler { id: connectionHover }
   ToolTip.visible: connectionHover.hovered
   ToolTip.text: bridge.updateConnection==="connected" ? win.tr("GitHub connected","GitHub 已连接") : bridge.updateConnection==="failed" ? win.tr("GitHub connection failed","GitHub 连接失败") : win.tr("GitHub not checked","尚未检测 GitHub")
  }
  EnglishText { id: currentVersion; objectName: "currentVersion"; x: 44; y: 660; text: bridge.version; color: "#829096"; font.pixelSize: 10 }
  ActionButton {
   id: updateLink; objectName: "checkUpdatesButton"
   x: currentVersion.x+currentVersion.implicitWidth+6; y: 649; width: Math.max(72,implicitContentWidth); height: 34
   // A newer program found by any check is only offered; this click starts its download.
   text: bridge.updateState==="available" ? "Update to "+bridge.updateVersion : "Check updates"
   leftPadding: 0; rightPadding: 0; showOutline: false; fill: "transparent"
   enabled: bridge.updateState!=="checking" && bridge.updateState!=="downloading" && bridge.updateState!=="ready"
   opacity: 1; ink: !enabled ? "#829074" : hovered || down || activeFocus ? "#d1ff9b" : "#a7eb52"
   background: Item {}
   font.family: currentVersion.font.family; font.pixelSize: currentVersion.font.pixelSize; font.underline: true
   contentItem: EnglishText { text: updateLink.text; color: updateLink.ink; font: updateLink.font; verticalAlignment: Text.AlignVCenter }
   onClicked: bridge.updateState==="available" ? bridge.startUpdate() : bridge.checkUpdates()
  }
  Item {
   id: footerProgressArea; objectName: "footerProgressArea"; x: Math.max(177,updateLink.x+updateLink.width+15); y: 649; width: 117; height: 34
   visible: bridge.footerStatus!==""
   property bool indeterminate: bridge.footerProgress<0
   property real motion: 0
   RioText {
    objectName: "footerStatusLabel"; x: 0; y: 0; width: footerPercent.visible ? 83 : 117; text: bridge.footerStatus
    color: "#a2b0b5"; font.pixelSize: 10; elide: Text.ElideRight
    HoverHandler { id: footerHover }
    ToolTip.visible: footerHover.hovered; ToolTip.text: bridge.footerStatus
   }
   EnglishText {
    id: footerPercent; objectName: "footerPercent"; x: 86; y: 0; width: 31
    text: Math.round(bridge.footerProgress*100)+"%"; visible: bridge.footerBusy && !footerProgressArea.indeterminate
    horizontalAlignment: Text.AlignRight; font.pixelSize: 10; color: "#a7eb52"
   }
   Rectangle {
    id: footerTrack; objectName: "footerProgressTrack"; x: 0; y: 25; width: 117; height: 4; radius: 2; color: "#303a3b"; clip: true
    visible: bridge.footerBusy
    Rectangle {
     id: footerFill; objectName: "footerProgressFill"
     width: footerTrack.width*(footerProgressArea.indeterminate ? 0.32 : Math.max(0,Math.min(1,bridge.footerProgress)))
     x: footerProgressArea.indeterminate ? (footerTrack.width-width)*footerProgressArea.motion : 0
     height: 4; radius: 2; color: "#a7eb52"
    }
   }
   NumberAnimation on motion {
    objectName: "footerProgressAnimation"; from: 0; to: 1; duration: 1000; loops: Animation.Infinite
    running: footerTrack.visible && footerProgressArea.indeterminate && win.visible
   }
  }
  ActionButton { objectName: "saveButton"; visible: win.tab===0; x: 310; y: 649; width: 90; height: 34; text: win.tr("Save","保存"); fill: "#a7eb52"; ink: "#17210f"; onClicked: bridge.saveAndHide() }
  }

 // Status line shared by every extension card: download state first, then a module update, then the module's own mode.
 function extensionDetail(ext,on,off){
  if(ext.state==="missing") return tr("Not downloaded","未下载 · 开启后下载")+(ext.downloadSize ? " · "+ext.downloadSize : "")
  if(ext.state==="downloading") return tr("Downloading ","正在下载 ")+Math.round(ext.progress*100)+"%"
  if(ext.state==="error") return tr("Download failed · Switch on to retry","下载失败 · 重新开启可重试")
  if(ext.updateState==="checking") return tr("Checking for updates…","正在检查更新…")
  if(ext.updateState==="latest") return tr("Up to date","已是最新版本")
  if(ext.updateState==="available") return tr("New version ","发现新版本 ")+ext.newVersion
  if(ext.updateState==="upgrading") return tr("Updating ","正在升级 ")+Math.round(ext.progress*100)+"%"
  if(ext.updateState==="installed") return tr("Updated to "+ext.newVersion+" · Applies after restart","已升级到 "+ext.newVersion+" · 重启后生效")
  if(ext.updateState==="failed") return tr("Update failed · Try again later","更新失败 · 稍后再试")
  return ext.enabled ? on : off
 }
 // One card per extension: name, module version and its update link, status line, optional mode switch and actions.
 component ExtensionCard: Item {
  default property alias actions: actionRow.data
  property alias accessory: accessorySlot.data
  property alias actionWidth: actionRow.width
  property var ext: null
  property string heading: ""
  property string detail: ""
  property real progress: ext && (ext.state==="downloading" || ext.updateState==="upgrading") ? ext.progress : -1
  property bool failed: ext !== null && (ext.state==="error" || ext.updateState==="failed")
  // A download or upgrade in progress keeps the switch where it is until it finishes.
  readonly property bool busy: ext !== null && (ext.state==="downloading" || ext.updateState==="upgrading")
  Layout.fillWidth: true; implicitHeight: 108
  FieldSurface { anchors.fill: parent }
  Column { x: 14; y: 12; width: parent.width-84; spacing: 3
   Row { id: titleRow; spacing: 6
    RioText { id: headingText; text: heading; color: "#edf0f2"; font.pixelSize: 15 }
    RioText { objectName: "moduleVersion"; anchors.baseline: headingText.baseline; text: ext ? ext.version : ""; color: "#89979f"; font.pixelSize: 10 }
    // The program's own link, per module: checks its index, then offers the version found; only that click upgrades.
    ActionButton {
     id: moduleLink; objectName: "moduleUpdateLink"; anchors.baseline: headingText.baseline
     readonly property string mode: ext ? ext.updateState : ""
     visible: ext !== null && ext.updatable; enabled: mode!=="checking" && mode!=="upgrading" && mode!=="installed"
     text: mode==="available" ? "Update to "+ext.newVersion : "Check updates"
     implicitHeight: 18; topPadding: 0; bottomPadding: 0; leftPadding: 0; rightPadding: 0; showOutline: false; fill: "transparent"
     opacity: 1; ink: !enabled ? "#829074" : hovered || down || activeFocus ? "#d1ff9b" : "#a7eb52"
     background: Item {}
     font.family: "Segoe UI"; font.pixelSize: 10; font.underline: true
     contentItem: EnglishText { text: moduleLink.text; color: moduleLink.ink; font: moduleLink.font; verticalAlignment: Text.AlignVCenter }
     onClicked: mode==="available" ? ext.upgrade() : ext.checkUpdate()
    }
   }
   RioText { width: parent.width; text: detail; color: failed ? "#eb7070" : "#89979f"; font.pixelSize: 10; elide: Text.ElideRight }
  }
  // Download and upgrade progress share the title line, between the version and the switch.
  Rectangle { objectName: "downloadTrack"; visible: progress>=0; x: 14+titleRow.width+12; y: 12+headingText.height/2-2
   width: Math.max(0,accessorySlot.x-12-x); height: 4; radius: 2; color: "#303a3b"
   Rectangle { width: parent.width*Math.max(0,Math.min(1,progress)); height: 4; radius: 2; color: "#a7eb52" }
  }
  Item { id: accessorySlot; x: parent.width-56; y: 14; width: 42; height: 24 }
  Row { id: actionRow; x: 14; y: parent.height-48; width: parent.width-28; height: 34; spacing: 8 }
 }
 DialogPopup {
  id: musicPopup; objectName: "musicPopup"; height: 410
  ColumnLayout { anchors.fill: parent; spacing: 12
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Music settings","音乐设置"); font.pixelSize: 17; color: "#edf0f2"; Layout.fillWidth: true } CloseButton { onClicked: musicPopup.close() } }
   RioText { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11; color: "#a6b7b0"; text: win.tr("Analyzes speaker audio locally. No microphone, recording files or audio uploads. Other apps' sounds may be included.","仅在本机分析输出声音，不使用麦克风，不保存或上传音频；可能包含其他应用声音。") }
   ComboBox { id: sourceChoice; Layout.fillWidth: true; implicitHeight: 36;
    background: Rectangle { color: "#11171b"; radius: 7; border.color: "#354047" }
    contentItem: RioText { text: sourceChoice.displayText; color: "#e5e8e9"; verticalAlignment: Text.AlignVCenter; leftPadding: 10; rightPadding: 24; elide: Text.ElideRight; font.pixelSize: 12 }
    indicator: RioText { x: sourceChoice.width-22; y: 8; text: "▾"; color: "#a7eb52" }
    delegate: ItemDelegate { width: sourceChoice.width; contentItem: RioText { text: modelData.label; color: "#e5e8e9"; elide: Text.ElideRight } background: Rectangle { color: highlighted ? "#354331" : "#1a2024" } }
    popup: Popup { y: sourceChoice.height; width: sourceChoice.width; padding: 2; background: Rectangle { color: "#1a2024"; radius: 6; border.color: "#354047" } contentItem: ListView { implicitHeight: Math.min(contentHeight,160); clip: true; model: sourceChoice.popup.visible ? sourceChoice.delegateModel : null; currentIndex: sourceChoice.highlightedIndex } }
 model: bridge.musicSources; textRole: "label"; valueRole: "id"; onActivated: bridge.setMusicSource(currentValue); Component.onCompleted: currentIndex=indexOfValue(bridge.musicSource) }
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Online lyrics","在线歌词"); color: "#edf0f2"; Layout.fillWidth: true } RioSwitch { id: lyricsToggle; checked: bridge.musicOnline; onToggled: { if(checked) lyricsConsent.open(); else bridge.setMusicOnline(false) } } }
   ActionButton { Layout.fillWidth: true; text: win.tr("Import LRC for current song","为当前歌曲导入 LRC"); onClicked: bridge.importMusicLyrics() }
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WrapAnywhere; font.pixelSize: 10; color: "#8c9c95"; text: bridge.musicStatus }
  }
 }
 DialogPopup {
  id: lyricsConsent; height: 278
  onClosed: lyricsToggle.checked=Qt.binding(function(){return bridge.musicOnline})
  ColumnLayout { anchors.fill: parent; spacing: 12
   RioText { text: win.tr("Online lyric matching","在线歌词匹配"); font.pixelSize: 17; color: "#edf0f2" }
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; font.pixelSize: 12; color: "#b2bdc4"; text: win.tr("Try the player's own lyric service first. If unavailable, query QQ Music, NetEase, Kugou and LRCLIB in parallel and display the first matching timed lyrics. Only song information is sent; never audio or account credentials.","先查询播放器自身的歌词服务；获取不到时，同时查询 QQ 音乐、网易云、酷狗和 LRCLIB，先返回匹配同步歌词的接口先显示。只发送歌曲信息，不发送音频或账号凭据。") }
   ConfirmationActions { onRejected: { bridge.setMusicOnline(false); lyricsConsent.close() } onAccepted: { bridge.setMusicOnline(true); lyricsConsent.close() } }
  }
 }
 DialogPopup {
  id: storagePopup; objectName: "storagePopup"
  onOpened: { bridge.prepareStoragePreview(); storageFileButton.forceActiveFocus() }
  closePolicy: bridge.storageWriting ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
  ColumnLayout {
   anchors.fill: parent; spacing: 14
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Screen content","屏幕内容"); color: "#edf0f2"; font.pixelSize: 17; Layout.fillWidth: true } CloseButton { objectName: "storageCloseButton"; Layout.preferredWidth: 26; enabled: !bridge.storageWriting; onClicked: storagePopup.close() } }
   ActionButton {
    id: storageFileButton; objectName: "chooseStorageButton"; Layout.fillWidth: true; implicitHeight: 40; fieldStyle: true
    text: win.tr("Choose file","选择文件"); enabled: !bridge.storageBusy; onClicked: bridge.chooseStorageFile()
   }
   Item {
    id: storagePreviewArea; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 80; clip: true
    property real previewSide: Math.min(128,Math.max(48,height-storageFilename.implicitHeight-storageFileInfo.implicitHeight-8))
    Column {
     anchors.centerIn: parent; width: parent.width; spacing: 4
     Item { anchors.horizontalCenter: parent.horizontalCenter; width: storagePreviewArea.previewSide; height: width
      AnimatedImage { anchors.fill: parent; source: bridge.storagePreview; playing: storagePopup.visible; fillMode: Image.PreserveAspectFit; visible: source.toString() !== "" }
      RioText { anchors.centerIn: parent; width: parent.width; wrapMode: Text.WordWrap; text: win.tr("Stored preview unavailable","暂无屏内内容预览"); color: "#819099"; horizontalAlignment: Text.AlignHCenter; visible: bridge.storagePreview === "" }
     }
     EnglishText { id: storageFilename; width: parent.width; text: bridge.storageName; color: "#edf0f2"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight }
     EnglishText { id: storageFileInfo; width: parent.width; text: bridge.storageDetail; color: "#91a0a9"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap }
    }
   }
   ProgressBar { visible: bridge.storageWriting; Layout.fillWidth: true; from: 0; to: 1; value: bridge.storageProgress
    background: Rectangle { implicitHeight: 4; color: "#354047"; radius: 2 }
    contentItem: Item { implicitHeight: 4; Rectangle { width: parent.width*(bridge.storageBusy && !bridge.storageWriting ? 0.3 : bridge.storageProgress); height: 4; radius: 2; color: "#a7eb52" } }
   }
   ActionButton { objectName: "writeStorageButton"; Layout.fillWidth: true; text: bridge.storageWriting ? Math.round(bridge.storageProgress*100)+"%" : win.tr("Write","写入"); fill: "#a7eb52"; ink: "#17210f"; enabled: bridge.storageReady && !bridge.storageBusy; onClicked: bridge.writeStorage() }
  }
 }
 DialogPopup {
  id: resetConfirmation; objectName: "resetConfirmation"; height: 136; visible: bridge.defaultConfirmation
  onClosed: if(bridge.defaultConfirmation) bridge.confirmRestoreDefault(false)
  ColumnLayout { anchors.fill: parent; spacing: 12
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; verticalAlignment: Text.AlignVCenter; text: win.tr("Restore default?","恢复默认动画？"); color: "#edf0f2"; font.pixelSize: 16 }
   ConfirmationActions { cancelObjectName: "cancelDefaultButton"; okObjectName: "confirmDefaultButton"; onRejected: bridge.confirmRestoreDefault(false); onAccepted: bridge.confirmRestoreDefault(true) }
  }
 }
 DialogPopup {
  id: cityPopup; objectName: "cityPopup"
  ColumnLayout {
   anchors.fill: parent; spacing: 14
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Choose your city","选择城市"); color: "#edf0f2"; font.pixelSize: 17; Layout.fillWidth: true } CloseButton { objectName: "cityCloseButton"; Layout.preferredWidth: 26; onClicked: cityPopup.close() } }
   TextField {
    id: searchField; objectName: "searchField"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: win.tr("Search city or region","搜索城市或地区"); color: "#edf0f2"; placeholderTextColor: "#7f8d95"; selectByMouse: true; leftPadding: 12; font.pixelSize: 13
    background: FieldSurface { highlighted: searchField.activeFocus || searchField.hovered }
    onAccepted: bridge.searchCities(text)
   }
   ListView {
    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 5; model: bridge.cityResults
    delegate: ActionButton {
     required property var modelData; required property int index
     width: ListView.view.width; height: 48; text: modelData.name
     contentItem: Column { RioText { text: modelData.name; color: "#e4e9eb"; font.pixelSize: 13 } RioText { text: modelData.detail; color: "#8e9ca4"; font.pixelSize: 10; elide: Text.ElideRight; width: parent.width } }
     onClicked: { bridge.selectCity(index); cityPopup.close() }
    }
    RioText { anchors.centerIn: parent; width: parent.width-20; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; text: bridge.searchStatus || win.tr("Type a city to search","输入城市名称后搜索"); color: "#8b99a1"; visible: bridge.cityResults.length===0; font.pixelSize: 12 }
   }
   ActionButton { Layout.fillWidth: true; text: win.tr("Search","搜索"); fill: "#a7eb52"; ink: "#17210f"; enabled: !bridge.searchBusy; onClicked: bridge.searchCities(searchField.text) }
  }
 }
 DialogPopup {
  id: consentPopup; objectName: "consentPopup"; height: 232
  ColumnLayout { anchors.fill: parent; spacing: 14
   RioText { text: win.tr("Locate your city","自动定位城市"); color: "#edf0f2"; font.pixelSize: 17 }
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; text: win.tr("Use ipwho.is to estimate your city from your public IP, and send approximate coordinates to Open-Meteo for weather.","使用 ipwho.is 根据公网 IP 估算城市，并将大致坐标发送给 Open-Meteo 获取天气。"); color: "#b2bdc4"; font.pixelSize: 13 }
   ConfirmationActions { cancelObjectName: "cancelLocateButton"; okObjectName: "confirmLocateButton"; onRejected: consentPopup.close(); onAccepted: { consentPopup.close(); bridge.locateCity() } }
  }
 }
 Popup { id: notice; popupType: Popup.Item; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 366; height: 190; modal: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  ColumnLayout { anchors.fill: parent; RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; text: bridge.notice; color: "#dce3e6"; font.pixelSize: 13 } ActionButton { Layout.alignment: Qt.AlignRight; text: win.tr("OK","确定"); Layout.preferredWidth: 80; onClicked: notice.close() } }
 }
 Connections { target: bridge; function onNoticeChanged() {if(bridge.notice) notice.open()} }
}

