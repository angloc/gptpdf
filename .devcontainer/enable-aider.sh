# Create the bin directory if it doesn't exist
mkdir -p ~/.local/bin

# Save the script
cat > ~/.local/bin/aider << 'EOF'
#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys

def check_env():
    # Check environment variables
    api_keys = {
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
        'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY')
    }
    
    # Check .env file if it exists
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    if value and key in api_keys and not api_keys[key]:
                        api_keys[key] = value.strip('"\'')

    # Check git configuration
    def get_git_config(key):
        try:
            return subprocess.check_output(['git', 'config', '--get', key], 
                                        stderr=subprocess.DEVNULL).decode().strip()
        except subprocess.CalledProcessError:
            return None

    git_user = get_git_config('user.name')
    git_email = get_git_config('user.email')
    
    errors = []
    
    # Check if at least one API key is present
    if not any(api_keys.values()):
        errors.append("Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set.\n"
                     "Please set one of them either in your environment or .env file")
    
    # Check git configuration
    if not git_user:
        errors.append('Git user.name is not set. Configure with:\n'
                     'git config --global user.name "Your Name"')
    if not git_email:
        errors.append('Git user.email is not set. Configure with:\n'
                     'git config --global user.email "your.email@example.com"')
    
    if errors:
        print("Configuration errors found:", file=sys.stderr)
        for error in errors:
            print(f"\n• {error}", file=sys.stderr)
        sys.exit(1)
    
    # Export the first available API key to be used by the container
    if api_keys['OPENAI_API_KEY']:
        os.environ['OPENAI_API_KEY'] = api_keys['OPENAI_API_KEY']
    elif api_keys['ANTHROPIC_API_KEY']:
        os.environ['ANTHROPIC_API_KEY'] = api_keys['ANTHROPIC_API_KEY']
    
    return api_keys

def main():

    # Check environment
    api_keys = check_env()

    # Get current user and group IDs
    uid = os.getuid()
    gid = os.getgid()

    # Construct the docker run command
    cmd = [
        'docker', 'run', '-it',
        f'--user={uid}:{gid}',
        f'--volume={os.getcwd()}:/app',
        '--env=OPENAI_API_KEY',
        '--env=ANTHROPIC_API_KEY',
        'paulgauthier/aider'
    ]

    # Add the appropriate API key flag
    if api_keys['OPENAI_API_KEY']:
        cmd.append(f'--openai-api-key={api_keys["OPENAI_API_KEY"]}')
    elif api_keys['ANTHROPIC_API_KEY']:
        cmd.append(f'--anthropic-api-key={api_keys["ANTHROPIC_API_KEY"]}')

    # Add any additional arguments
    cmd.extend(sys.argv[1:])

    # Execute the command
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        sys.exit(130)

if __name__ == '__main__':
    main()
EOF

# Make it executable
chmod +x ~/.local/bin/aider

# Make sure ~/.local/bin is in your PATH
# Add this to your ~/.bashrc or ~/.zshrc if it's not already there:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc  # or ~/.zshrc for zsh