import { html } from "/assets/vendor/arrow-core.js";
import { hideSidebar, upperFirst } from "/assets/js/utils.js";

const MENU_ITEMS = {
  home: [
    { name: "首页", link: "/", icon: "bi-house-fill" },
  ],
  recordings: [
    { name: "行车记录", link: "/dashcam_routes", icon: "bi-camera-reels" },
    { name: "屏幕录像", link: "/screen_recordings", icon: "bi-record-circle" },
  ],
  tools: [
    { name: "设置开关", link: "/device_settings", icon: "bi-toggle-on" },
    { name: "下载限速", link: "/download_speed_limits", icon: "bi-download" },
    { name: "错误日志", link: "/manage_error_logs", icon: "bi-exclamation-triangle" },
    { name: "Galaxy 云", link: "/galaxy", icon: "bi-globe2" },
    { name: "哨兵模式", link: "/sentry", icon: "bi-shield-exclamation" },
    { name: "转向调校", link: "/tuning", icon: "bi-sign-turn-right" },
    { name: "纵向操作", link: "/longitudinal_maneuvers", icon: "bi-signpost-split" },
    { name: "地图", link: "/manage_maps", icon: "bi-map" },
    { name: "导航", link: "/set_navigation_destination", icon: "bi-geo-alt-fill" },
    { name: "应用密钥", link: "/manage_navigation_keys", icon: "bi-key-fill" },
    { name: "模型管理", link: "/manage_models", icon: "bi-cpu" },
    { name: "图表", link: "/plots", icon: "bi-graph-up-arrow" },
    { name: "测试场", link: "/testing_ground", icon: "bi-bezier2" },
    { name: "故障排查", link: "/troubleshoot", icon: "bi-tools" },
    { name: "V-ASM 侧方监测", link: "/manage_v_asm", icon: "bi-eye" },
    { name: "画中画侧摄像头", link: "/manage_pip_sidecam", icon: "bi-badge-hd", developerOnly: true },
    { name: "主题制作", link: "/theme_maker", icon: "bi-palette-fill" },
    { name: "Tmux 日志", link: "/manage_tmux", icon: "bi-terminal" },
    { name: "备份与恢复", link: "/manage_toggles", icon: "bi-arrow-repeat" },
    { name: "软件更新", link: "/manage_updates", icon: "bi-arrow-up-circle" },
    { name: "车辆功能", link: "/vehicle_features", icon: "bi-car-front" },
  ],
};

let galaxyDeveloperMode = false;

function matchesPath(currentPath, link) {
  if (link === "/") return currentPath === "/";
  if (link === "/tuning" && currentPath === "/lateral_maneuvers") return true;
  return currentPath === link || currentPath.startsWith(`${link}/`);
}

function buildSectionMarkup(section, links, currentPath) {
  const sectionNames = { home: "主页", recordings: "录像", tools: "工具" };
  const sectionTitle = sectionNames[section] || section;
  const linksMarkup = links.filter((link) => !link.developerOnly || galaxyDeveloperMode).map((link) => {
    const active = matchesPath(currentPath, link.link) ? "active" : "";
    return `
      <li class="${active}">
        <a class="menu-item-link" href="${link.link}">
          <i class="bi ${link.icon}"></i>
          <span>${upperFirst(link.name)}</span>
        </a>
      </li>
    `;
  }).join("");

  return `
    <div class="sidebar_widget">
      <ul class="menu_section">
        <li>
          <span class="section-title">${sectionTitle}</span>
          <ul id="${section}">
            ${linksMarkup}
          </ul>
        </li>
      </ul>
    </div>
  `;
}

async function refreshGalaxyDeveloperMode() {
  try {
    const response = await fetch("/api/params/all", { cache: "no-store" });
    if (!response.ok) return;
    const values = await response.json();
    const next = Boolean(values?.GalaxyDeveloperMode);
    if (next !== galaxyDeveloperMode) {
      galaxyDeveloperMode = next;
      renderSidebarIntoShell();
    }
  } catch (error) {
    console.warn("Unable to determine Galaxy Developer Mode:", error);
  }
}

function bindSidebarHandlers() {
  const menuButton = document.getElementById("menu_button");
  const underlay = document.getElementById("sidebarUnderlay");

  if (!menuButton || !underlay) return;

  if (!window.__theGalaxySidebarMenuBound) {
    window.__theGalaxySidebarMenuBound = true;
    menuButton.addEventListener("click", () => {
      const sidebar = document.getElementById("sidebar");
      const currentUnderlay = document.getElementById("sidebarUnderlay");
      if (!sidebar || !currentUnderlay) return;
      sidebar.classList.toggle("visible");
      currentUnderlay.classList.toggle("hidden");
    });
  }

  underlay.onclick = hideSidebar;

  document.querySelectorAll("#sidebar a.menu-item-link").forEach((anchor) => {
    if (anchor.dataset.boundClick === "1") return;
    anchor.dataset.boundClick = "1";
    anchor.addEventListener("click", (event) => {
      if (event.defaultPrevented) return;
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      event.preventDefault();
      const href = anchor.getAttribute("href") || "/";
      const navigate = window.__theGalaxyNavigate;
      if (typeof navigate === "function") {
        navigate(href);
      } else {
        window.location.assign(href);
      }
      hideSidebar();
      window.scrollTo(0, 0);
    });
  });
}

function renderSidebarIntoShell(currentPath) {
  const shell = document.getElementById("sidebar_shell");
  if (!shell) return;

  const activePath = currentPath || window.location.pathname;
  const sectionsMarkup = Object.entries(MENU_ITEMS)
    .map(([section, links]) => buildSectionMarkup(section, links, activePath))
    .join("");

  shell.innerHTML = `
    <div id="sidebarUnderlay" class="hidden"></div>
    <div id="sidebar" class="sidebar">
      <div>
        <div class="title">
          <img class="logo" src="/assets/images/main_logo.png" alt="Galaxy logo" />
          <div class="title_text sidebar_header">
            <p>Galaxy</p>
          </div>
        </div>
        <hr />
        ${sectionsMarkup}
      </div>
    </div>
  `;

  bindSidebarHandlers();
}

export function Sidebar(currentPath) {
  setTimeout(() => {
    renderSidebarIntoShell(currentPath);
    refreshGalaxyDeveloperMode();
  }, 0);
  return html`<div id="sidebar_shell"></div>`;
}
