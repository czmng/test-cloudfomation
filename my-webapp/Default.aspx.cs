using System;
using System.Web.UI;

namespace MyWebApp
{
    public partial class Default : Page
    {
        protected void Page_Load(object sender, EventArgs e)
        {
            // 如果环境变量 APP_VERSION 或 APP_VERSION_COLOR 未设置，设置默认值
            if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("APP_VERSION")))
            {
                Environment.SetEnvironmentVariable("APP_VERSION", "Unknown Version");
            }
            if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("APP_VERSION_COLOR")))
            {
                // 可以根据版本号设置颜色，例如 "BLUE" 或 "GREEN"
                string version = Environment.GetEnvironmentVariable("APP_VERSION");
                if (version.Contains("BLUE")) {
                    Environment.SetEnvironmentVariable("APP_VERSION_COLOR", "blue");
                } else if (version.Contains("GREEN")) {
                    Environment.SetEnvironmentVariable("APP_VERSION_COLOR", "green");
                } else {
                    Environment.SetEnvironmentVariable("APP_VERSION_COLOR", "orange");
                }
            }
        }
    }
}