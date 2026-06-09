Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\jun_0\Desktop\Claude"
WshShell.Run "python.exe ""C:\Users\jun_0\Desktop\Claude\monitor.py""", 0, False
