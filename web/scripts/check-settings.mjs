// Browser-independent component checks; never connects to Android or a profile.
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const server=await createServer({server:{middlewareMode:true},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
try {
  const {SettingsPanel}=await server.ssrLoadModule('/src/SettingsPanel.tsx');
  const props={fields:[{key:'gui_theme',label:'Theme',description:'Preview immediately',kind:'choice',choices:['Modern','Ember'],section:'Interface',advanced:false}],
    values:{gui_theme:'Ember'},search:'',setSearch(){},advanced:false,setAdvanced(){},dirty:false,saving:false,restarting:false,
    saveDisabled:false,resetDisabled:false,save(){},reset(){},edit(){}};
  const render=changes=>renderToStaticMarkup(React.createElement(SettingsPanel,{...props,...changes}));
  const clean=render({});assert.ok(clean.includes('Theme'));assert.ok(!clean.includes('Отменить изменения'));assert.ok(!clean.includes('Сохранить изменения'));
  assert.ok(!clean.includes('account-context'));assert.ok(!clean.includes('>Stop<'));
  const appearance=render({dirty:true});assert.ok(appearance.includes('Сохранить изменения'));assert.ok(!appearance.includes('Сохранить и перезапустить'));
  assert.ok(render({dirty:true,restarting:true}).includes('Сохранить и перезапустить'));
  assert.ok(render({dirty:true,saving:true}).includes('Применение…'));
  const {harborPalette,paletteProperties}=await server.ssrLoadModule('/src/interfacePalettes.ts');
  function luminance(hex){
    const rgb=hex.match(/[0-9a-f]{2}/gi).map(x=>parseInt(x,16)/255)
      .map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);
    return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
  }
  function contrast(a,b){const values=[luminance(a),luminance(b)].sort((a,b)=>a-b);return (values[1]+.05)/(values[0]+.05);}
  for(const palette of [harborPalette]){
    for(const surface of [palette.bg,palette.sidebar,palette.surface,palette.surface_hover]){
      for(const ink of [palette.text,palette.text_secondary,palette.accent,palette.error,palette.success])
        assert.ok(contrast(ink,surface)>=4.5,ink+' on '+surface+' needs readable contrast');
    }
    assert.ok(contrast(palette.accent_fg,palette.accent)>=4.5);
    assert.ok(contrast('#ffffff',palette.danger)>=4.5);
    assert.ok(contrast('#ffffff',palette.cobalt)>=4.5);
    assert.ok(contrast(palette.border,palette.field_bg)>=3,'Input boundaries need 3:1 contrast');
    for(const meter of [palette.gold,palette.elixir,palette.dark_elixir])
      assert.ok(contrast(meter,palette.surface)>=3);
    assert.equal(paletteProperties(palette)['--field-bg'],palette.field_bg);
    assert.equal(palette.appearance,'light');

  }
  console.log('Settings component checks passed');
  console.log('UniCode palette: readable text, actions, fields, and resource meters passed');
} finally {await server.close();}
