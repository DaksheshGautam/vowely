Option Explicit
Dim Files, Shell, Root, App, Python, Command
Set Files = CreateObject("Scripting.FileSystemObject")
Set Shell = CreateObject("WScript.Shell")
Root = Files.GetParentFolderName(WScript.ScriptFullName)
App = Files.BuildPath(Root, "app\Vowely\Vowely.exe")
If Files.FileExists(Files.BuildPath(Root, "app-prerelease\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-prerelease\Vowely\Vowely.exe")
End If
If Files.FileExists(Files.BuildPath(Root, "app-formatting\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-formatting\Vowely\Vowely.exe")
End If
If Files.FileExists(Files.BuildPath(Root, "app-comma-lists\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-comma-lists\Vowely\Vowely.exe")
End If
If Files.FileExists(Files.BuildPath(Root, "app-orb\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-orb\Vowely\Vowely.exe")
End If
If Files.FileExists(Files.BuildPath(Root, "app-automatic\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-automatic\Vowely\Vowely.exe")
End If
If Files.FileExists(Files.BuildPath(Root, "app-final-insertion\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-final-insertion\Vowely\Vowely.exe")
End If
If Files.FileExists(Files.BuildPath(Root, "app-branding\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-branding\Vowely\Vowely.exe")
End If
If Files.FileExists(Files.BuildPath(Root, "app-learning\Vowely\Vowely.exe")) Then
    App = Files.BuildPath(Root, "app-learning\Vowely\Vowely.exe")
End If
Python = Files.BuildPath(Root, ".venv\Scripts\pythonw.exe")
If Files.FileExists(App) Then
    Command = Chr(34) & App & Chr(34) & " --root " & Chr(34) & Root & Chr(34)
ElseIf Files.FileExists(Python) Then
    Command = Chr(34) & Python & Chr(34) & " -m localflow.launcher --root " & Chr(34) & Root & Chr(34)
Else
    MsgBox "Vowely runtime is missing. Follow SETUP.md to install or build it.", 16, "Vowely"
    WScript.Quit 1
End If
Shell.Run Command, 1, False
