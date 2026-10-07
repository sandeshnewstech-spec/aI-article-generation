const regex = /^[A-Za-z0-9\.\,\-\/\(\)\:\;\!\?\@\#\$\%\&\*\+\=\'\"\[\]\{\}\“\”\‘\’]+$/;
console.log('Test 1:', regex.test('જાહેર'));
console.log('Test 2:', regex.test('GARDEN'));
console.log('Test 3:', regex.test('**'));
console.log('Test 4:', regex.test('ક/જેહા'));
