const fs = require('fs');

let code = fs.readFileSync('app/static/js/unicode_to_gopika.js', 'utf8');
// Mock window object
let window = {};
eval(code);

console.log(unicodeToGopika("ક્ષેત્રફળ"));
console.log(unicodeToGopika("શેત્રફણ"));
console.log(unicodeToGopika("જાહેર"));
