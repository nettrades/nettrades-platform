!macro customInstall
    SetOutPath "$INSTDIR\service"
    File "service\nettrades-netsvc.exe"
    File "service\tunnel.dll"
    File "service\wireguard.dll"
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" install'
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" start'
!macroend

!macro customUnInstall
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" stop'
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" uninstall'
!macroend