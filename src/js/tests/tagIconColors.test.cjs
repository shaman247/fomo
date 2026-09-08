const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function manager(palette){
    const ctx=vm.createContext({
        document:{body:{classList:{contains:()=>false}}},
        Utils:{getCurrentTheme:()=> 'test'},
        Themes:{resolve:()=>({base:'dark',chipColors:palette?'palette':'emoji'})},
        IconManager:{tagCacheKey:tag=>tag==='Bingo'?'bingo-revision':''}
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../tags/tagColorManager.js'),'utf8')+'\nthis.manager=TagColorManager;',ctx);
    ctx.manager.init({darkPalette:['#123456'],lightPalette:[],tagEmojiMap:{}});
    return ctx.manager;
}
test('loaded tag artwork updates the selected tag color',()=>{
    const m=manager(false);
    assert.equal(m.assignColorToTag('Bingo'),'#8899aa');
    m.acceptTagIconColor('Bingo','#ff0000');
    assert.equal(m.getTagColor('Bingo'),'#ff0000');
    m.unassignColorFromTag('Bingo');
    assert.equal(m.assignColorToTag('Bingo'),'#ff0000');
});
test('palette-based themes retain their assigned chip colors',()=>{
    const m=manager(true);
    assert.equal(m.assignColorToTag('Bingo'),'#123456');
    assert.equal(m.acceptTagIconColor('Bingo','#ff0000'),'#123456');
    assert.equal(m.getTagColor('Bingo'),'#123456');
});
