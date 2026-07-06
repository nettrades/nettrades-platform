# Visual Studio Code Setup Guide for NETTRADES Platform

This guide provides detailed, step-by-step instructions for setting up Visual Studio Code to work with the NETTRADES Platform repository.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Installing Visual Studio Code](#installing-visual-studio-code)
3. [Installing Git](#installing-git)
4. [Connecting to GitHub](#connecting-to-github)
5. [Cloning the Repository](#cloning-the-repository)
6. [Configuring Git](#configuring-git)
7. [Recommended Extensions](#recommended-extensions)
8. [Working with Branches](#working-with-branches)
9. [Common Git Operations](#common-git-operations)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

- Windows 10/11, macOS, or Linux
- Internet connection
- GitHub account ([sign up here](https://github.com/join))

## Installing Visual Studio Code

### Windows
1. Visit [code.visualstudio.com](https://code.visualstudio.com/)
2. Click the **Download for Windows** button
3. Run the installer (`VSCodeUserSetup-x64-*.exe`)
4. Check "Add 'Open with Code' action" and "Add to PATH"
5. Click "Next" and "Install"
6. Launch VS Code after installation

### macOS
1. Visit [code.visualstudio.com](https://code.visualstudio.com/)
2. Click **Download for Mac**
3. Open the downloaded `.zip` file
4. Drag `Visual Studio Code.app` to the `Applications` folder
5. Launch from Applications

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install wget gpg
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
sudo sh -c 'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
rm -f packages.microsoft.gpg
sudo apt update
sudo apt install code


## Installing Git

### Windows

#### Option A: Using VS Code Terminal (Recommended)

* Open VS Code

* Open the integrated terminal: Ctrl+`

Run:

```powershell

    winget install --id Git.Git -e --source winget
```
* Close and reopen VS Code

* Verify instalation: 

```powershell    
    git --version (should show version number)
```
#### Option B: Manual Installation

* Visit [git-scm.com/download/win](https://git-scm.com/download/win)

* Download the 64-bit installer

* Run the installer with default settings

* Restart VS Code

### macOS

bash

# Using Homebrew
brew install git

# Using Xcode Command Line Tools
xcode-select --install

### Linux (Ubuntu/Debian)

bash

sudo apt update
sudo apt install git -y

### Connecting to GitHub

#### Method 1: GitHub Authentication (Recommended)

* In VS Code, click the Accounts icon in the bottom-left corner

* Select "Sign in with GitHub"

* A browser window will open – log into GitHub

* Click "Authorize Visual Studio Code"

* Return to VS Code – you should see your GitHub username

#### Method 2: Personal Access Token

* On GitHub, go to Settings ? Developer settings ? Personal access tokens

* Generate a new token with repo and workflow scopes

* Copy the token

* In VS Code, when prompted for credentials, paste the token

### Cloning the Repository

#### Option A: Clone via VS Code GUI (Easiest)

* Press Ctrl+Shift+P to open Command Palette

* Type and select Git: Clone

* Enter repository URL:
    
```text
    https://github.com/nettrades/nettrades-platform.git
```
* From the dropdown, select dev-deployment1

* Choose destination folder (e.g., C:\Projects\ or ~/Projects/)

* Click "Select Repository Location"

* Click "Open" when prompted

#### Option B: Clone via VS Code Terminal

Open VS Code

Open terminal: Ctrl+`

Navigate to destination:
```    bash

    cd /path/to/your/projects
```

Clone the specific branch:
```    bash

    git clone -b dev-deployment1 https://github.com/nettrades/nettrades-platform.git
```

Open in VS Code:
```    bash

    cd nettrades-platform
    code .
```
#### Option C: Clone via Source Control Panel

* Press Ctrl+Shift+G to open Source Control

* Click "Clone Repository"

* Enter URL and branch

* Follow the prompts

### Configuring Git

After cloning, configure Git with your information:
```bash

# Set your name (required for commits)
git config --global user.name "Your Full Name"

# Set your email (use GitHub email)
git config --global user.email "your.email@example.com"

# Set VS Code as default Git editor
git config --global core.editor "code --wait"

# Set default branch name
git config --global init.defaultBranch main

# Enable colored output
git config --global color.ui auto
```

### Recommended Extensions

Install these VS Code extensions for the best experience:
Essential Extensions
text

?? Python - Python language support
?? Docker - Docker container management  
?? GitLens - Enhanced Git features
?? YAML - YAML syntax highlighting
?? Markdown All in One - Markdown editing
?? Prettier - Code formatting

### Additional Helpful Extensions
text

?? Remote - SSH - Connect to remote servers
?? REST Client - API testing
?? Todo Tree - Task management in comments
?? indent-rainbow - Visual indentation
?? Path Intellisense - Path autocomplete

#### Installing Extensions

* Click the Extensions icon in left sidebar (Ctrl+Shift+X)

* Search for extension name

* Click Install

### Working with Branches

#### View All Branches
```bash

git branch
# Or in VS Code: click branch name in status bar
```
#### Create a New Branch
```bash

# Create and switch to new branch
git checkout -b feature/your-feature

# VS Code: Click branch name ? "Create new branch"
```
#### Switch to Existing Branch
```bash

git checkout dev-deployment1

# VS Code: Click branch name ? Select from dropdown
```
#### Merge Branches
```bash

# From dev-deployment1, merge main
git checkout dev-deployment1
git merge origin/main -m "Merge main into dev-deployment1"
```
#### Resolve Merge Conflicts

* Open conflicting file (highlighted in red)

VS Code shows conflict markers:
```    text

    <<<<<<< HEAD
    your changes
    =======
    incoming changes  
    >>>>>>> branch-name
```
* Use the inline buttons: "Accept Current", "Accept Incoming", or "Accept Both"

* Stage and commit the resolved file

### Common Git Operations

#### In VS Code Terminal

| Operation | Command |
|---------|-------------|	
| `Check status` | `git status` |
| `Stage all changes` | `git add .` |
| `Stage specific file` | `git add filename` |
| `Commit with message` | `git commit -m "message"` |
| `Push to remote` | `git push origin dev-deployment1` |
| `Pull from remote` | `git pull origin dev-deployment1` |
| `View commit history` | `git log --oneline` |
| `Discard changes` | `git checkout -- filename` |
| `View diff` | `git diff` |

#### In VS Code GUI

| Operation | VS Code Action |
|---------|-------------|
| `Stage changes` | `Click + next to file in Source Control` |
| `Commit` | `Type message in Source Control, click ?` |
| `Push/Pull` | `Click "..." in Source Control` |
| `View changes` | `Click file in Source Control` |
| `Diff` | `Click file ? "View Diff"` |
| `Undo changes` | `Click "" in Source Control` |

### Troubleshooting
#### Issue: git: command not found

##### Solution:

* Install Git via winget or web download

* Restart VS Code completely

* On Windows, check C:\Program Files\Git\bin exists

#### Issue: Authentication Failed

##### Solution:

* Click Accounts icon in VS Code bottom-left

* Sign out and sign back in to GitHub

* Generate a new Personal Access Token

#### Issue: "There are no staged changes"

##### Solution:

* Stage changes first: click + button or run git add .

* Then commit

#### Issue: Merge Conflict

##### Solution:

* Open conflicting file

* Use VS Code's conflict resolution buttons

* Stage resolved file (git add filename)

* Commit (git commit -m "Resolved merge conflict")

#### Issue: "Failed to push" error

##### Solution:

* Pull latest changes first: git pull origin dev-deployment1

* Resolve any conflicts

* Push again: git push origin dev-deployment1

#### Issue: VS Code doesn't show Git features

##### Solution:

* Ensure Git is installed: git --version in terminal

* Reload VS Code window: Ctrl+Shift+P ? "Reload Window"

* Check Git is enabled: File ? Preferences ? Settings ? "Git: Enabled"

#### Still stuck

* [GitHub Issues](https://github.com/nettrades/nettrades-platform/issues)

* [VS Code Documentation](https://code.visualstudio.com/docs)

* [Git Documentation](https://git-scm.com/doc)