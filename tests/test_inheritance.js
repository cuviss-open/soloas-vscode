const assert = require('assert');
const db = require('../language-server/src/database.ts');
const root = db.GetRootNamespace();
function type(name, superclass, interfaces = []) {
    const result = new db.DBType();
    result.name = name;
    result.supertype = superclass;
    result.interfaces = interfaces;
    db.AddTypeToDatabase(root, result);
    return result;
}
const base = type('ITestBase', null);
const child = type('ITestChild', null, ['ITestBase']);
const object = type('UTestObject', null);
const cls = type('UTestClass', 'UTestObject', ['ITestChild']);
assert.ok(child.inheritsFrom('ITestBase'));
assert.ok(cls.inheritsFrom('ITestChild'));
assert.ok(cls.inheritsFrom('ITestBase'));
assert.ok(cls.inheritsFrom('UTestObject'));
assert.ok(!base.inheritsFrom('UTestClass'));
console.log('Interface inheritance type relationships: passed');
