import os
from webui import webui

win = webui.Window()

def main():
    
    current_folder = os.path.dirname(os.path.abspath(__file__))
    win.set_root_folder(current_folder)
    win.set_size(1440, 900)

    # Биндим функции из HTML
    win.bind("goToProperties", open_properties)
    win.bind("goToLanguages", open_language)
    win.bind("goToInformation", open_info)
    win.bind("Exit", appExit)
    win.show("main.html")
    webui.wait()

def open_properties(event: webui.Event):
    print("Properities")
    win.show("main.html")
    webui.wait()

def open_language(event: webui.Event):
    print("Languages")
    win.show("languages.html")
    webui.wait()

def open_info(event: webui.Event):
    print("Information")
    win.show("information.html")
    webui.wait()

def appExit(event: webui.Event):
    print("Exit")
    webui.exit()

if __name__ == "__main__":
    main()

