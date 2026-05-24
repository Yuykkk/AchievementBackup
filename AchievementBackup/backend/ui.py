import subprocess
import threading

def show_notification(title, message):
    def _run():
        ps_script = f"""
        $ErrorActionPreference = 'SilentlyContinue'
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);
        $textNodes = $template.GetElementsByTagName("text");
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null;
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null;
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("AchievementBackup");
        $notification = [Windows.UI.Notifications.ToastNotification]::new($template);
        $notifier.Show($notification);
        """
        
        try:
            subprocess.run(["powershell", "-Command", ps_script], creationflags=0x08000000)
        except Exception as e:
            print(f"[AchievementBackup] Erro ao enviar notificação: {e}")

    threading.Thread(target=_run, daemon=True).start()