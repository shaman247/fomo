const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function manager(){
    const ctx=vm.createContext({
        document:{body:{classList:{contains:()=>false}}},
        Utils:{getCurrentTheme:()=> 'dark'},
        IconManager:{tagCacheKey:tag=>tag==='Bingo'?'bingo-revision':''}
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../tags/tagColorManager.js'),'utf8')+'\nthis.manager=TagColorManager;',ctx);
    ctx.manager.init({darkPalette:['#123456'],lightPalette:[],tagEmojiMap:{}});
    return ctx.manager;
}
test('loaded tag artwork updates the selected tag color',()=>{
    const m=manager();
    assert.equal(m.assignColorToTag('Bingo'),'#8899aa');
    m.acceptTagIconColor('Bingo','#ff0000');
    assert.equal(m.getTagColor('Bingo'),'#ff0000');
    m.unassignColorFromTag('Bingo');
    assert.equal(m.assignColorToTag('Bingo'),'#ff0000');
});
