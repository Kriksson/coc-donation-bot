export type InterfacePalette={
  appearance:'dark'|'light';bg:string;sidebar:string;surface:string;surface_hover:string;
  text:string;text_secondary:string;border:string;accent:string;accent_fg:string;
  danger:string;error:string;warning:string;success:string;field_bg:string;
  gold:string;elixir:string;dark_elixir:string;
  cobalt:string;brass:string;
};
// Shared light palette matches the local UniCode interface.
export const harborPalette:InterfacePalette={
  appearance:'light',bg:'#ffffff',sidebar:'#faf9f8',surface:'#ffffff',surface_hover:'#f5f2ef',
  text:'#302b28',text_secondary:'#746861',border:'#998e87',accent:'#ce3030',accent_fg:'#ffffff',
  danger:'#b52c32',error:'#aa3038',warning:'#94651f',success:'#44774f',field_bg:'#ffffff',
  gold:'#b48a38',elixir:'#a16aa3',dark_elixir:'#75708d',cobalt:'#d73737',brass:'#d73737',
};

export function paletteProperties(palette:InterfacePalette){
  return Object.fromEntries(Object.entries(palette).filter(([key])=>key!=='appearance')
    .map(([key,value])=>['--'+key.replaceAll('_','-'),value]));
}
