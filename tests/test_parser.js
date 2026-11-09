const assert = require('assert');
const parser = require('../language-server/pegjs/angelscript');
const nodes = require('../language-server/grammar/node_types');
const parse = (text, startRule = 'start', opts = {}) => parser.parse(text, {startRule, ...opts});
const iface = parse('interface IFoo : IBase, IOther', 'start_global');
assert.strictEqual(iface.isInterface, true);
assert.deepStrictEqual(iface.interfaces.map(x => x.value), ['IBase', 'IOther']);
const cls = parse('class UChild : UObject, IFoo, IOther', 'start_global');
assert.strictEqual(cls.superclass.value, 'UObject');
assert.deepStrictEqual(cls.interfaces.map(x => x.value), ['IFoo', 'IOther']);
for (const method of ['BindLambda', 'AddLambda', 'Sort', 'StableSort', 'KeySort', 'ValueSort']) {
    const ast = parse(`Target.${method}([int Number, FString Text](int A, int B) { if (A < B) { Print("}"); } return Number < A; })`);
    const lambda = ast.children[1].children[0];
    assert.strictEqual(lambda.type, nodes.LambdaExpression);
    assert.deepStrictEqual(lambda.captures.map(x => x.name.value), ['Number', 'Text']);
    assert.deepStrictEqual(lambda.parameters.map(x => x.name.value), ['A', 'B']);
}
for (const [text, rule] of [
    ['class UOld : UObject', 'start_global'],
    ['struct FOld', 'start_global'],
    ['void Existing(int Value)', 'start_global'],
    ['void Existing(int Value)', 'start_class'],
    ['Values[Index]', 'start'],
    ['Values.Sort(Other)', 'start'],
    ['Cast<UObject>(Value).Name', 'start'],
]) assert.ok(parse(text, rule, {precedesBlock: true}), text);
console.log('PEG syntax and existing syntax: passed');
