# Perzforge — Phase 0 Setup Guide (Detailed Edition)

**Hardware:** ASUS TUF F15 (i5-12500H, 16GB, GTX 1650 Ti) · **OS target:** Ubuntu 26.04 LTS
**Done when:** you can SSH into the laptop from your phone on mobile data and run `nvidia-smi` inside a Docker container.

**Two tracks:**
- **Track A — WSL2 (start today, no USB needed):** full GPU + Docker + remote access on Windows. Everything you build ports to real Ubuntu later.
- **Track B — Dual-boot (the real deal, needs a 16GB USB ~₹300):** do this when the USB arrives.

Do Track A now, Track B later. They don't conflict.

---

# TRACK A — WSL2 Interim Setup (today, ~45 min)

## A1. Prerequisites check
1. **Windows version:** press `Win+R` → type `winver` → Enter. You need Windows 10 21H2+ or any Windows 11. (A 12th-gen TUF almost certainly shipped with 11.)
2. **Virtualization enabled:** `Ctrl+Shift+Esc` → Performance tab → CPU → look for "Virtualization: Enabled" bottom-right.
   - If **Disabled**: reboot → tap `F2` → Advanced → enable "Intel Virtualization Technology (VT-x)" → `F10` save.
3. **NVIDIA driver current:** open GeForce Experience (or nvidia.com/drivers) and update to the latest Game Ready driver. ⚠️ **This Windows driver is the ONLY GPU driver you need — never install a Linux NVIDIA driver inside WSL.** WSL2 uses the Windows driver through a passthrough layer.

## A2. Install WSL2 + Ubuntu
1. Right-click Start → **Terminal (Admin)**.
2. Run:
   ```powershell
   wsl --install -d Ubuntu-24.04
   ```
   *(Microsoft Store WSL images may lag the newest release; 24.04 is fine here — the WSL track is temporary scaffolding. If `Ubuntu-26.04` appears in `wsl --list --online`, use that instead.)*
3. **Reboot when prompted.** After reboot a terminal opens automatically to finish setup.
4. Create your Linux username (suggest: `harsh`) and password when asked. This is separate from your Windows password.
5. Verify and pin WSL2 mode:
   ```powershell
   wsl --update
   wsl --set-default-version 2
   wsl --list --verbose     # your distro should show VERSION 2
   ```
6. Quick GPU sanity check *inside* WSL (open the Ubuntu app):
   ```bash
   nvidia-smi
   ```
   ✅ Should print your GTX 1650 Ti. Yes, without installing anything — the Windows driver provides this. If it fails, your Windows NVIDIA driver is too old (step A1.3).

## A3. Docker Desktop with GPU
1. Download **Docker Desktop for Windows** from docker.com → install → reboot if asked.
2. Open Docker Desktop → ⚙️ Settings:
   - **General:** ✅ "Use the WSL 2 based engine"
   - **Resources → WSL Integration:** ✅ toggle ON for your Ubuntu distro
3. Apply & Restart.
4. **The Track A money shot** — in the Ubuntu terminal:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```
   ✅ GPU printed from inside a container = your ML job runner has a home. 🎉

## A4. Tailscale (remote access)
1. Download **Tailscale for Windows** from tailscale.com/download → install.
2. Click the tray icon → Log in → sign in with Google/GitHub (this creates your tailnet).
3. Note your IP: tray icon → your machine name → the `100.x.y.z` address.
4. Go to **login.tailscale.com** → Machines → your laptop → ⋯ menu → **Disable key expiry** (otherwise it silently drops off in ~90–180 days).
5. Install the **Tailscale app on your phone**, log into the same account.

## A5. SSH access (phone → laptop)
Cleanest on Windows: use the built-in OpenSSH Server, then hop into WSL.
1. Settings → System → Optional features → **Add a feature** → install **"OpenSSH Server"**.
2. Terminal (Admin):
   ```powershell
   Set-Service sshd -StartupType Automatic
   Start-Service sshd
   ```
3. On your phone: install **Termius** (free tier is fine) → New Host → address = your Tailscale `100.x.y.z` → username = your **Windows** username → Windows password.
4. **The milestone test:** phone on mobile data (WiFi OFF) → connect. You land in Windows PowerShell → type `wsl` → you're in Ubuntu. From anywhere on Earth.

## A6. Keep it awake
Settings → System → Power → **"When plugged in, put my device to sleep" → Never**. (Screen can still turn off — that's fine.)

**Track A caveats to accept:** the "server" only exists while Windows is awake; WSL2's network is NAT'd behind Windows (fine for now — the FastAPI/Redis/Postgres dev work in Phase 1 doesn't care); real systemd services and Incus come with Track B.

---

# TRACK B — Dual-Boot Ubuntu 26.04 (when the USB arrives, ~2–3 hrs)

## B0. Shopping list
- 1× USB drive, **16GB+** (₹250–400 — SanDisk/HP from any shop or Amazon/Flipkart). You'll reuse it: first as recovery drive, then re-flash as Ubuntu installer. If you can stretch to 2× USBs, keep the recovery drive permanently — safer.

## B1. Protect Windows (30 min, do NOT skip any of this)
1. **Back up your files** — anything irreplaceable goes to cloud/external drive now.
2. **BitLocker check** — Terminal (Admin):
   ```powershell
   manage-bde -status C:
   ```
   - "Protection On" → **first** save the recovery key: `manage-bde -protectors -get C:` → photograph the 48-digit key / save to your Microsoft account. **Then** suspend it: Control Panel → BitLocker → "Suspend protection" (or fully "Turn off BitLocker" — takes a while to decrypt but is the safest for dual-boot).
   - "Protection Off" → move on.
3. **Create the recovery drive:** Start → search "Create a recovery drive" → ✅ "Back up system files" → select your USB → Create (~20–30 min, wipes the USB).
   - After it's done and IF you only have one USB: you'll re-flash this same USB with Ubuntu in step B3. The recovery *files* are gone then, but you verified the process works and your BitLocker key + file backups are safe. (Two USBs = keep both. Recommended.)
4. **Disable Fast Startup:** Control Panel → Power Options → "Choose what the power buttons do" → "Change settings that are currently unavailable" → uncheck **Turn on fast startup** → Save.
   - *Why:* Fast Startup half-hibernates Windows, which locks the disk and can corrupt data when another OS touches it.

## B2. Carve out disk space (10 min)
1. Right-click Start → **Disk Management**.
2. Identify your main disk (the TUF usually has one NVMe, maybe two). Right-click the big **C:** partition → **Shrink Volume…**
3. In "Enter the amount of space to shrink in MB": type `153600` (=150GB) or minimum `102400` (=100GB).
   - If Windows offers less than you want, the blocker is immovable system files: disable hibernation temporarily (`powercfg /h off` in admin terminal), reboot, retry, re-enable later (`powercfg /h on`).
4. Click Shrink. You now see a black **"Unallocated"** block. **Leave it exactly like that** — do not create a partition, do not format. Close Disk Management.

## B3. Make the Ubuntu USB (15 min)
1. Download the **Ubuntu 26.04 LTS Desktop** ISO from **ubuntu.com/download/desktop** (~6GB).
2. *(Optional but proper)* Verify the download — admin terminal, in your Downloads folder:
   ```powershell
   certutil -hashfile .\ubuntu-26.04-desktop-amd64.iso SHA256
   ```
   Compare with the SHA256 listed on Ubuntu's download page. Match = file isn't corrupted/tampered.
3. Download **Rufus** (rufus.ie) → run it:
   - Device: your USB
   - Boot selection: the Ubuntu ISO
   - Partition scheme: **GPT** · Target system: **UEFI (non CSM)**
   - Everything else: defaults → **START** → if asked, choose "Write in ISO Image mode" → OK (wipes the USB).

## B4. BIOS settings (5 min)
1. Reboot → hammer **F2** during the ASUS logo → BIOS.
2. Press **F7** for Advanced Mode if you land in EZ Mode.
3. **Security tab → Secure Boot → Secure Boot Control → Disabled.**
   - *Why:* avoids NVIDIA driver signature (MOK) complications. Windows 11 still boots fine. You can re-enable later once everything works, if you're willing to do MOK enrollment.
4. **Advanced tab** (while you're here): if you see **"Restore AC Power Loss"** → set **Power On** (auto-boot after power cuts — Prayagraj summers will thank you).
5. **F10** → Save & Exit.

## B5. Install Ubuntu (30 min)
1. Plug in the USB → reboot → hammer **Esc** (or F8) during the ASUS logo → boot menu → pick the USB (the "UEFI: …" entry).
2. GRUB menu → "Try or Install Ubuntu" → wait for the installer.
3. Walkthrough:
   - Language: English → "Install Ubuntu"
   - Keyboard: English (US) — or whatever your physical layout is
   - **Connect to WiFi** (matters: pulls updates + NVIDIA components during install)
   - Applications: **Default/Normal selection** · ✅ **"Install third-party software for graphics and Wi-Fi hardware"**
   - **Installation type — the critical screen:** choose **"Install Ubuntu alongside Windows Boot Manager."** It auto-uses your unallocated space.
     - If that option is missing: pick **"Manual/Something else"** → click the **"free space"** entry → `+` → Size: all of it → Type: Ext4 → Mount point: `/` → OK. **Do not touch** any NTFS partition or the ~100–260MB "EFI System Partition". Bootloader device: leave default.
   - Timezone: Kolkata
   - Your name/computer name/username: keep username short (`harsh`), hostname something you'll recognize on the network (`perzforge-node`), **strong password**.
4. Install → "Restart Now" → pull out the USB when told → Enter.
5. You should now see the **GRUB menu**: `Ubuntu` / `Windows Boot Manager`.
   - **Immediately test Windows once** (select it, let it boot, shut down, boot back to Ubuntu). Confirming both OSes work *now* beats discovering a problem in week 3.
   - No GRUB, straight into Windows? → BIOS (F2) → Boot tab → move **"ubuntu"** above "Windows Boot Manager" → F10.

## B6. First-boot Ubuntu setup (10 min)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential curl git htop net-tools
```
Fix the dual-boot clock skew (Windows and Linux disagree about hardware-clock timezone; without this, Windows shows the wrong time after every Ubuntu session):
```bash
sudo timedatectl set-local-rtc 1 --adjust-system-clock
```

## B7. NVIDIA driver (10 min)
```bash
sudo ubuntu-drivers list          # see what's recommended
sudo ubuntu-drivers autoinstall   # installs the recommended driver
sudo reboot
```
After reboot:
```bash
nvidia-smi
```
✅ Expect: `GeForce GTX 1650 Ti`, a driver version, `4096MiB` memory.
❌ "NVIDIA-SMI has failed / couldn't communicate with the driver":
1. Secure Boot still enabled? → B4.3.
2. `lsmod | grep nvidia` empty? → `sudo apt install nvidia-driver-570` (or whatever `ubuntu-drivers list` marked "recommended") → reboot.
3. Check nothing blacklisted it: `grep -r nouveau /etc/modprobe.d/` (the installer normally handles this).

*Note: 26.04 also ships CUDA natively in the repos (`sudo apt install cuda-toolkit` if you ever want CUDA on the host). For Perzforge you don't need it on the host — CUDA lives inside job containers.*

## B8. Docker (5 min)
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```
**Log out and back in** (or `newgrp docker`) so the group applies, then:
```bash
docker run hello-world
```

## B9. NVIDIA Container Toolkit (10 min)
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```
**The Track B money shot:**
```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```
*(Container OS version ≠ host OS version — irrelevant by design. Any recent `nvidia/cuda` tag works.)*
✅ GPU visible inside the container = Perzforge's GPU node officially exists.

## B10. Tailscale (5 min)
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
1. Open the URL it prints → authenticate → done.
2. `tailscale ip -4` → note the `100.x.y.z`. **Write it down** — this is your server's permanent address.
3. **login.tailscale.com** → Machines → this machine → ⋯ → **Disable key expiry**.
4. Phone already has Tailscale from Track A; both machines (Windows/Ubuntu are separate tailnet entries) will show up.

## B11. SSH — enable, test, then harden (15 min)
**Enable:**
```bash
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
```
**Test from phone (mobile data, WiFi off):** Termius → new host → the Ubuntu Tailscale IP → username `harsh` → password → connect. ✅ Milestone.

**Now harden — order matters:**
1. In Termius: Keychain → generate an **ED25519 keypair** → copy the **public** key.
2. On the server:
   ```bash
   mkdir -p ~/.ssh
   nano ~/.ssh/authorized_keys      # paste the public key, one line, save
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/authorized_keys
   ```
   *(Wrong permissions here are the #1 reason key auth mysteriously fails — sshd refuses world-readable key files.)*
3. In Termius, attach the key to the host and **verify key-based login works** while password auth is still on.
4. ⚠️ **Keep your current SSH session open** as a lifeline, then in a second session:
   ```bash
   sudo nano /etc/ssh/sshd_config
   ```
   Set (uncomment where needed):
   ```
   PasswordAuthentication no
   PermitRootLogin no
   PubkeyAuthentication yes
   ```
   ```bash
   sudo systemctl restart ssh
   ```
5. From the phone: disconnect, reconnect with the key. Works? Hardened. Doesn't? Your lifeline session fixes the config.

**Firewall + brute-force protection:**
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow in on tailscale0
sudo ufw enable          # answer y
sudo ufw status verbose  # verify: deny incoming, allow on tailscale0

sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```
*(With UFW denying all non-Tailscale inbound, SSH is unreachable from your home LAN too — that's intended. Everything goes through Tailscale, including you.)*

## B12. Laptop-as-server tweaks (10 min)
**Run with the lid closed:**
```bash
sudo nano /etc/systemd/logind.conf
```
Uncomment/set:
```
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```
```bash
sudo systemctl restart systemd-logind
```
**Battery longevity — cap charge at 80%** (mandatory for a plugged-in-24/7 laptop; prevents swelling):
```bash
echo 80 | sudo tee /sys/class/power_supply/BAT0/charge_control_end_threshold
```
Make it survive reboots — create a tiny systemd unit:
```bash
sudo tee /etc/systemd/system/battery-cap.service > /dev/null << 'EOF'
[Unit]
Description=Cap battery charge at 80%

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'echo 80 > /sys/class/power_supply/BAT0/charge_control_end_threshold'

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable battery-cap.service
```
**Disable sleep entirely** (it's a server now):
```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

---

# ✅ Exit Checklists

**Track A (WSL2) done when:**
- [ ] `nvidia-smi` works inside WSL Ubuntu
- [ ] GPU container test passes in Docker Desktop
- [ ] SSH from phone on mobile data via Tailscale → `wsl`
- [ ] Windows never sleeps when plugged in

**Track B (dual-boot) done when:**
- [ ] GRUB shows both OSes; **both boot**
- [ ] `nvidia-smi` on host ✓ and inside container ✓
- [ ] SSH from phone on mobile data, **key-only** (password login rejected)
- [ ] `ufw status`: deny incoming / allow on tailscale0; fail2ban active
- [ ] Lid-close ignored; battery capped at 80% and persists after reboot; sleep masked
- [ ] Tailscale key expiry disabled

**→ Phase 1:** repo with `/docs` (PRD + architecture), FastAPI skeleton, docker-compose for Postgres+Redis, user stories A2 → B1.

---

# Troubleshooting Table

| Symptom | Fix |
|---|---|
| WSL: `nvidia-smi` not found | Update the **Windows** NVIDIA driver; never install Linux drivers in WSL |
| WSL install error 0x80370102 | Virtualization disabled in BIOS → A1.2 |
| Docker: "could not select device driver with capabilities gpu" | Track A: WSL integration off in Docker Desktop settings. Track B: rerun B9's `nvidia-ctk` + `systemctl restart docker` |
| No GRUB after install | BIOS boot order: "ubuntu" first (B5.5) |
| `nvidia-smi` fails on dual-boot | Secure Boot still on → disable (B4.3); or driver missing → B7 |
| Shrink Volume won't give enough space | `powercfg /h off`, reboot, retry, `powercfg /h on` after |
| Key-based SSH refuses, password works | Permissions: `chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`; key must be one unbroken line |
| Locked out of SSH after hardening | Use the physical keyboard; you also kept a session open like B11.4 said |
| Tailscale works on WiFi, not mobile data | Phone's Tailscale toggle off, or battery saver killed the VPN — whitelist the app |
| Windows clock wrong after Ubuntu | `sudo timedatectl set-local-rtc 1 --adjust-system-clock` (B6) |
| Windows asks for BitLocker key after GRUB install | Enter the 48-digit key you saved in B1.2 (this is exactly why you saved it), then re-suspend BitLocker |
| Battery cap resets after reboot | The systemd unit in B12 handles this; check `systemctl status battery-cap` |
