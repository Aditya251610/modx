import * as vscode from 'vscode';
import * as path from 'path';
import * as child_process from 'child_process';

export function activate(context: vscode.ExtensionContext) {
    console.log('ModX VS Code extension is now active!');

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('modx.analyze', async (uri: vscode.Uri) => {
            await runModxCommand(uri, 'analyze');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('modx.plan', async (uri: vscode.Uri) => {
            await runModxCommand(uri, 'plan');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('modx.migrate', async (uri: vscode.Uri) => {
            await runModxCommand(uri, 'migrate');
        })
    );
}

async function runModxCommand(uri: vscode.Uri, command: string) {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
    if (!workspaceFolder) {
        vscode.window.showErrorMessage('Please open a workspace folder first.');
        return;
    }

    const terminal = vscode.window.createTerminal('ModX');
    terminal.show();

    // Check if modx is installed
    const modxPath = await findModxExecutable();
    if (!modxPath) {
        vscode.window.showErrorMessage(
            'ModX CLI not found. Please install ModX first: pip install -e .'
        );
        return;
    }

    // Build command
    let cmd = `${modxPath} ${command}`;
    if (command === 'plan' || command === 'migrate') {
        const relativePath = path.relative(workspaceFolder.uri.fsPath, uri.fsPath);
        cmd += ` --service "${relativePath || '.'}"`;
    }

    // For migrate, add interactive flag
    if (command === 'migrate') {
        cmd += ' --interactive';
    }

    terminal.sendText(cmd);
}

async function findModxExecutable(): Promise<string | null> {
    // Try common locations
    const candidates = [
        'modx',  // If in PATH
        './.venv/bin/modx',  // Virtual env
        './venv/bin/modx',
        'python -m modx.cli'  // Direct module
    ];

    for (const candidate of candidates) {
        try {
            await new Promise((resolve, reject) => {
                child_process.exec(`${candidate} --help`, (error) => {
                    if (error) reject(error);
                    else resolve(true);
                });
            });
            return candidate;
        } catch {
            continue;
        }
    }

    return null;
}

export function deactivate() {}