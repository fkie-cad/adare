import subprocess
import dataclasses
import re
from PIL import ImageDraw

import logging
log = logging.getLogger(__name__)

@dataclasses.dataclass
class Window:
    id: int
    name: str
    x: int
    y: int
    width: int
    height: int
    hidden: bool = dataclasses.field(default=False)
    shadow: tuple[int,int,int,int] = dataclasses.field(default_factory=lambda: (0, 0, 0, 0))
    identifiers: list[str] = dataclasses.field(default_factory=list)
    non_visible_areas: list[tuple[int, int, int, int]] = dataclasses.field(default_factory=list)

    @property
    def rect(self):
        return (self.x + self.shadow[0], self.y + self.shadow[1],
                self.width - self.shadow[0] - self.shadow[2],
                self.height - self.shadow[1] - self.shadow[3])


def is_desktop_window(window_id):
    try:
        output = subprocess.check_output(["xprop", "-id", str(window_id), "_NET_WM_WINDOW_TYPE"]).decode()
        return "_NET_WM_WINDOW_TYPE_DESKTOP" in output
    except subprocess.CalledProcessError:
        return False


def get_window_stacking():
    command = ["xprop", "-root", "_NET_CLIENT_LIST_STACKING"]
    output = subprocess.check_output(command).decode()
    _, window_ids = output.split("window id # ")
    window_ids = window_ids.split(", ")
    window_ids = [window_id.strip() for window_id in window_ids if window_id.strip()]
    window_ids = [int(window_id, 16) for window_id in window_ids]
    window_ids.reverse()
    return window_ids

def get_window_info(window_id):
    command = ["xwininfo", "-id", str(window_id)]
    output = subprocess.check_output(command).decode()
    lines = output.splitlines()
    name = ""
    x = y = width = height = -1
    for line in lines:
        if "Absolute upper-left X:" in line:
            x = int(line.split(":")[1].strip())
        elif "Absolute upper-left Y:" in line:
            y = int(line.split(":")[1].strip())
        elif "Width:" in line:
            width = int(line.split(":")[1].strip())
        elif "Height:" in line:
            height = int(line.split(":")[1].strip())
        elif "Window id:" in line:
            name = line.split(" ")[-1].strip()

    xprop_command = ["xprop", "-id", str(window_id)]
    output = subprocess.check_output(xprop_command).decode()
    hidden = "_NET_WM_STATE_HIDDEN" in output
    shadow = (0, 0, 0, 0)
    if "_GTK_FRAME_EXTENTS(CARDINAL)" in output:
        # GTK applications may have frame extents that we need to account for
        gtk_frame_extents = output.split("_GTK_FRAME_EXTENTS(CARDINAL) = ")[1].split('\n')[0].split(', ')
        shadow = tuple(int(extent) for extent in gtk_frame_extents)
    return Window(id=window_id, name=name, x=x, y=y, width=width, height=height, hidden=hidden, shadow=shadow, identifiers=[])


def rect_intersection(a, b, consider_shadow=True):
    """Returns the intersection rectangle of a and b, or None if they don't overlap."""
    if consider_shadow:
        ax1, ay1, ax2, ay2 = a.x + a.shadow[0], a.y + a.shadow[1], a.x + a.width - a.shadow[2], a.y + a.height - a.shadow[3]
        bx1, by1, bx2, by2 = b.x + b.shadow[0], b.y + b.shadow[1], b.x + b.width - b.shadow[2], b.y + b.height - b.shadow[3]
    else:
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.width, a.y + a.height
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.width, b.y + b.height

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix1 < ix2 and iy1 < iy2:
        return (ix1, iy1, ix2 - ix1, iy2 - iy1)
    return None


def subtract_rect(base, cut):
    """
    Subtract `cut` rectangle from `base` rectangle.
    Returns list of up to 4 rectangles representing the remaining area.
    base and cut are (x, y, w, h).
    """
    bx, by, bw, bh = base
    cx, cy, cw, ch = cut

    # Boundaries of each
    bx2, by2 = bx + bw, by + bh
    cx2, cy2 = cx + cw, cy + ch

    # Find intersection
    ix1 = max(bx, cx)
    iy1 = max(by, cy)
    ix2 = min(bx2, cx2)
    iy2 = min(by2, cy2)

    # If no intersection, return base as-is
    if ix1 >= ix2 or iy1 >= iy2:
        return [base]

    result = []

    # Top slice (above the cut)
    if by < iy1:
        result.append((bx, by, bw, iy1 - by))
    # Bottom slice (below the cut)
    if iy2 < by2:
        result.append((bx, iy2, bw, by2 - iy2))
    # Left slice (left of the cut)
    if bx < ix1:
        result.append((bx, iy1, ix1 - bx, iy2 - iy1))
    # Right slice (right of the cut)
    if ix2 < bx2:
        result.append((ix2, iy1, bx2 - ix2, iy2 - iy1))

    return result



def calculate_overlap(windows: list[Window]):
    for i, window in enumerate(windows):
        full_rect = window.rect
        non_visible = []

        for above in windows[:i]:
            overlap = rect_intersection(window, above)
            if overlap:
                non_visible.append(overlap)

        remaining = [full_rect]
        for nv in non_visible:
            updated = []
            for region in remaining:
                updated.extend(subtract_rect(region, nv))
            remaining = updated

        # After subtracting all occlusions from full rect, what remains is visible
        # So we subtract visible regions from full rect to get true non-visible regions
        final_non_visible = [full_rect]
        for visible in remaining:
            updated = []
            for region in final_non_visible:
                updated.extend(subtract_rect(region, visible))
            final_non_visible = updated

        window.non_visible_areas = final_non_visible


def get_windows_by_search_string(search_string: str) -> list[Window]:
    try:
        window_ids = subprocess.check_output(
            ["xdotool", "search", "--any", search_string]
        ).decode().splitlines()
    except subprocess.CalledProcessError:
        log.warning(f"No windows found matching: {search_string}")
        return []

    window_ids = [int(window_id.strip(), 10) for window_id in window_ids if window_id.strip()]
    windows = []

    for window_id in window_ids:
        try:
            xwininfo_output = subprocess.check_output([
                "xwininfo", "-id", str(window_id)
            ]).decode()
            xprop_output = subprocess.check_output([
                "xprop", "-id", str(window_id)
            ]).decode()
        except subprocess.CalledProcessError:
            log.warning(f"Failed to get window info for ID {window_id}")
            continue

        if "IsViewable" not in xwininfo_output:
            log.debug(f"Window {window_id} is not viewable, skipping.")
            continue

        # Filter based on size
        if re.search(r"Width:\s+1\s*\n\s*Height:\s+1", xwininfo_output):
            log.debug(f"Window {window_id} is 1x1, skipping.")
            continue

        # Filter based on negative position
        if re.search(r"Absolute upper-left X:\s*-\d+", xwininfo_output) or \
           re.search(r"Absolute upper-left Y:\s*-\d+", xwininfo_output):
            log.debug(f"Window {window_id} is off-screen, skipping.")
            continue

        # Skip if it has SKIP_TASKBAR or SKIP_PAGER state
        if "_NET_WM_STATE_SKIP_TASKBAR" in xprop_output or "_NET_WM_STATE_SKIP_PAGER" in xprop_output:
            log.debug(f"Window {window_id} is skipping taskbar/pager, skipping.")
            continue

        # Skip if override redirect
        if "Override Redirect State: yes" in xwininfo_output:
            log.debug(f"Window {window_id} has override redirect, skipping.")
            continue

        log.info(f"Found valid window ID: {window_id}")
        windows.append(get_window_info(window_id))

    return windows


def get_visible_windows():
    windows = get_window_stacking()
    visible_windows = []
    for window_id in windows:
        if is_desktop_window(window_id):
            continue
        window = get_window_info(window_id)
        if window.hidden:
            continue
        visible_windows.append(window)
    calculate_overlap(visible_windows)
    filtered_windows = []
    for window in visible_windows:
        if not window.non_visible_areas or not all(
            (area == window.rect) for area in window.non_visible_areas
        ):
            filtered_windows.append(window)
    for window in filtered_windows:
        log.info(f"Window ID: {window.id}, Name: {window.name}, "
              f"Position: ({window.x}, {window.y}), Size: ({window.width}x{window.height}), "
              f"Non-visible areas: {window.non_visible_areas}")
    return filtered_windows


def get_os_info():
    """Get Linux OS information."""
    import subprocess

    info = {}

    try:
        # Get OS release info
        with open('/etc/os-release', 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip('"')
                    if key == 'NAME':
                        info['name'] = value
                    elif key == 'VERSION':
                        info['version'] = value
                    elif key == 'VERSION_ID':
                        info['version_id'] = value
    except FileNotFoundError:
        pass

    try:
        # Get kernel info
        result = subprocess.run(['uname', '-r'], capture_output=True, text=True)
        if result.returncode == 0:
            info['kernel'] = result.stdout.strip()
    except FileNotFoundError:
        pass

    try:
        # Get architecture
        result = subprocess.run(['uname', '-m'], capture_output=True, text=True)
        if result.returncode == 0:
            info['architecture'] = result.stdout.strip()
    except FileNotFoundError:
        pass

    return info


def detect_package_manager():
    """Detect which package manager is available, preferring dpkg for Debian and rpm for RedHat."""
    import subprocess
    import os

    # Check for Debian-based systems first
    if os.path.exists('/etc/debian_version'):
        try:
            subprocess.run(['which', 'dpkg'], capture_output=True, check=True)
            return 'dpkg'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # Check for RedHat-based systems
    if os.path.exists('/etc/redhat-release'):
        try:
            subprocess.run(['which', 'rpm'], capture_output=True, check=True)
            return 'rpm'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # Fallback to other package managers
    other_managers = ['pacman', 'zypper']

    for manager in other_managers:
        try:
            subprocess.run(['which', manager], capture_output=True, check=True)
            return manager
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    return None


def get_installed_packages(manager=None):
    """Get list of installed packages using detected package manager."""
    import subprocess

    if manager is None:
        manager = detect_package_manager()

    if manager is None:
        return []

    packages = []

    try:
        if manager == 'dpkg':
            result = subprocess.run(['dpkg', '-l'], capture_output=True, text=True)
            if result.returncode == 0:
                packages = _parse_dpkg_output(result.stdout)

        elif manager == 'rpm':
            result = subprocess.run(['rpm', '-qa'], capture_output=True, text=True)
            if result.returncode == 0:
                packages = _parse_rpm_output(result.stdout)

        elif manager == 'pacman':
            result = subprocess.run(['pacman', '-Q'], capture_output=True, text=True)
            if result.returncode == 0:
                packages = _parse_pacman_output(result.stdout)

        elif manager == 'zypper':
            result = subprocess.run(['zypper', 'search', '--installed-only'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                packages = _parse_zypper_output(result.stdout)

    except subprocess.CalledProcessError as e:
        log.warning(f"Failed to get packages with {manager}: return code {e.returncode}")
    except FileNotFoundError as e:
        log.warning(f"Package manager {manager} not found: {e}")
    except Exception as e:
        log.warning(f"Unexpected error getting packages with {manager}: {e}")

    return packages


def _parse_dpkg_output(output):
    """Parse dpkg -l output."""
    packages = []
    for line in output.split('\n'):
        line = line.strip()
        if line.startswith('ii'):
            parts = line.split()
            if len(parts) >= 3:
                packages.append({'name': parts[1], 'version': parts[2]})
    return packages


def _parse_rpm_output(output):
    """Parse rpm -qa output."""
    packages = []
    for line in output.split('\n'):
        line = line.strip()
        if '-' in line:
            parts = line.rsplit('-', 2)
            if len(parts) >= 2:
                name = parts[0]
                version = '-'.join(parts[1:])
                packages.append({'name': name, 'version': version})
    return packages


def _parse_pacman_output(output):
    """Parse pacman -Q output."""
    packages = []
    for line in output.split('\n'):
        line = line.strip()
        parts = line.split()
        if len(parts) >= 2:
            packages.append({'name': parts[0], 'version': parts[1]})
    return packages


def _parse_zypper_output(output):
    """Parse zypper search output."""
    packages = []
    for line in output.split('\n'):
        line = line.strip()
        parts = line.split()
        if parts and not parts[0].startswith('#'):
            package_info = {'name': parts[0]}
            if len(parts) > 1:
                package_info['version'] = parts[1]
            packages.append(package_info)
    return packages

