<%@ Page Language="C#" AutoEventWireup="true" CodeFile="Default.aspx.cs" Inherits="MyWebApp.Default" %>

<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head runat="server">
    <title>My Simple AWS Web App</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; background-color: #f0f8ff; color: #333; }
        h1 { color: #0056b3; }
        .version { font-weight: bold; color: <%= System.Environment.GetEnvironmentVariable("APP_VERSION_COLOR") %>; }
        .container { border: 1px solid #ddd; padding: 20px; border-radius: 8px; max-width: 600px; margin: 30px auto; background-color: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <form id="form1" runat="server">
        <div class="container">
            <h1>Welcome to My AWS Web App!</h1>
            <p>This is <span class="version">Version <%= System.Environment.GetEnvironmentVariable("APP_VERSION") %></span> deployed via AWS CodeDeploy.</p>
            <p>Deployed at: <%= DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") %></p>
            <p>Hostname: <%= System.Net.Dns.GetHostName() %></p>
            <hr />
            <p>This application is powered by Amazon EC2 for Microsoft Windows Server.</p>
        </div>
    </form>
</body>
</html>