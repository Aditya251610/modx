// MODX_DETERMINISTIC_FALLBACK: aggressive modernization applied
const express = require('express');
const app = express();

app.get('/', (req, res) => {
    let message = "Hello from legacy JavaScript service";
    let version = "1.0";
    res.send(message + ` version ${ version }`);
});

const greet = (name) => {
    return `Hello ${ name }`;
}

app.listen(3000, () => {
    console.log('Server running on port 3000');
});