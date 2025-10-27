#!/usr/bin/env node
// Lightweight Node wrapper that forwards arguments to the Python ModX CLI
// It will try common python launchers on the system and forward all args.

import { spawn } from 'child_process';

const args = process.argv.slice(2);
const pythonModuleArgs = ['-m', 'modx.cli', ...args];

const candidates = [
  { cmd: 'python3', prefix: [] },
  { cmd: 'python', prefix: [] },
  // Windows py launcher
  { cmd: 'py', prefix: ['-3'] }
];

function tryCandidate(index) {
  if (index >= candidates.length) {
    console.error('Error: No Python runtime found (tried python3, python, py -3). Please install Python 3 and ensure it is on your PATH.');
    process.exit(127);
    return;
  }

  const candidate = candidates[index];
  const spawnArgs = candidate.prefix.concat(pythonModuleArgs);
  const child = spawn(candidate.cmd, spawnArgs, { stdio: 'inherit' });

  child.on('error', (err) => {
    // If the executable was not found, try the next candidate
    if (err && (err.code === 'ENOENT' || err.code === 'ENOTDIR')) {
      tryCandidate(index + 1);
    } else {
      console.error('Failed to start Python process:', err.message || err);
      process.exit(1);
    }
  });

  child.on('close', (code, signal) => {
    if (signal) {
      // Propagate signal
      try {
        process.kill(process.pid, signal);
      } catch (e) {
        // ignore
      }
      return;
    }
    process.exit(typeof code === 'number' ? code : 0);
  });
}

tryCandidate(0);
