' TEOIGO Launcher — Ejecuta teoigo_client.pyw SIN consola visible
' Usa python.exe (no pythonw.exe) para evitar falsos positivos de antivirus.
' La ventana de consola se oculta con WindowStyle=0.

Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
clientPath = fso.BuildPath(scriptDir, "teoigo_client.pyw")

' Buscar python.exe
pythonPath = ""

' Intentar con where
Set exec = WshShell.Exec("cmd /c where python 2>nul")
Do While Not exec.StdOut.AtEndOfStream
    line = Trim(exec.StdOut.ReadLine())
    ' Tomar el primero que NO sea WindowsApps (ese es el store stub)
    If line <> "" And InStr(LCase(line), "windowsapps") = 0 Then
        pythonPath = line
        Exit Do
    End If
Loop

If pythonPath = "" Then
    MsgBox "No se encontro python.exe en el PATH." & vbCrLf & _
           "Reinstala Python marcando 'Add to PATH'.", _
           vbCritical, "TEOIGO - Error"
    WScript.Quit 1
End If

' Lanzar python con ventana oculta (0 = vbHide)
WshShell.Run """" & pythonPath & """ """ & clientPath & """", 0, False
