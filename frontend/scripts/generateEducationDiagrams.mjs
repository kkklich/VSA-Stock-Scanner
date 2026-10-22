// Reproducible, bilingual diagrams. All prices/volumes are synthetic examples.
// Run from any directory: node frontend/scripts/generateEducationDiagrams.mjs
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { definitions } from './educationDiagramDefinitions.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const destination = path.join(root, 'public/education/definitions')
const colors = { bg: '#0b1425', panel: '#111e33', grid: '#24364f', ink: '#e7edf7', muted: '#a6b8cf', up: '#34d399', down: '#fb7185', gold: '#fbbf24', blue: '#38bdf8', purple: '#c4b5fd' }
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]))
const local = (value, lang) => Array.isArray(value) ? value[lang === 'en' ? 0 : 1] : value
const line = (x1,y1,x2,y2,color=colors.grid,dash='') => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="2" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`
const rect = (x,y,w,h,fill,rx=0,opacity=1) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" opacity="${opacity}"/>`
const circle = (x,y,r,color) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${color}"/>`
const text = (x,y,value,size=24,color=colors.ink,anchor='start') => `<text x="${x}" y="${y}" font-size="${size}" fill="${color}" text-anchor="${anchor}">${escape(value)}</text>`
function words(value, length=48) {
  const lines = ['']
  for (const word of String(value).split(' ')) {
    const i = lines.length - 1
    if (lines[i] && lines[i].length + word.length + 1 > length) lines.push(word)
    else lines[i] += (lines[i] ? ' ' : '') + word
  }
  return lines
}
const wrapped = (x,y,value,width=48,size=24,color=colors.ink,anchor='start') => words(value,width).map((t,i)=>text(x,y+i*(size+7),t,size,color,anchor)).join('')
const pathLine = (points,color,width=4) => `<polyline points="${points.map(p=>p.join(',')).join(' ')}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linejoin="round" stroke-linecap="round"/>`
function candle(x, b, y, width=36) {
  const [open,high,low,close] = b
  if (high < Math.max(open,close) || low > Math.min(open,close) || low > high) throw new Error(`Invalid OHLC: ${b}`)
  const color = close >= open ? colors.up : colors.down
  return line(x,y(high),x,y(low),color) + rect(x-width/2,Math.min(y(open),y(close)),width,Math.max(3,Math.abs(y(open)-y(close))),color,2)
}
function chart(scene,lang) {
  const bars = scene.bars
  const levels = scene.levels ?? []
  const prices = [...bars.flatMap(b=>[b[1],b[2]]),...levels.map(l=>l[0])]
  const low = Math.min(...prices), high = Math.max(...prices), span = high-low || 1
  const y = p=>350 - (p-low+span*.10)/(span*1.20)*196
  const x = i=>90+i*630/(bars.length-1)
  const volumes = bars.map(b=>b[4]??100)
  const vmax = Math.max(...volumes,scene.volumeRef??0)*1.1
  const vy = v=>467-v/vmax*91
  const width = Math.min(38,490/bars.length)
  let svg = (scene.labels?'':text(48,133,lang==='en'?'PRICE':'CENA',16,colors.muted))+text(48,376,'V',16,colors.muted)
  for (const yy of [160,208,256,304,350,467]) svg+=line(64,yy,752,yy)
  let labelBottom=140
  for (const [p,label,color] of [...levels].sort((a,b)=>b[0]-a[0])) {
    const labelTop=Math.max(y(p)-12,labelBottom)
    const labelText=local(label,lang)
    svg+=line(64,y(p),752,y(p),color??colors.blue,'7 7')+line(752,y(p),764,labelTop+8,color??colors.blue)+wrapped(770,labelTop+18,labelText,15,20,color??colors.blue)
    labelBottom=labelTop+words(labelText,15).length*27+8
  }
  for (let i=0;i<bars.length;i++) {
    const active = (scene.highlight??[bars.length-1]).includes(i)
    if(active) svg+=rect(x(i)-width,145,width*2,328,colors.gold,8,.06)
    svg+=candle(x(i),bars[i],y,width)
    svg+=rect(x(i)-width/2,vy(volumes[i]),width,467-vy(volumes[i]),active?colors.gold:(bars[i][3]>=bars[i][0]?colors.up:colors.down),2,.9)
    if(active) svg+=circle(x(i),y(bars[i][3]),5,colors.gold)
  }
  if (scene.volumeRef) svg+=line(64,vy(scene.volumeRef),752,vy(scene.volumeRef),colors.purple,'7 7')+wrapped(770,vy(scene.volumeRef)+6,local(scene.volumeLabel??'V ref',lang),15,20,colors.purple)
  if (scene.labels) for(const [i,label] of scene.labels) svg+=text(x(i),122,local(label,lang),20,colors.gold,'middle')
  svg+=text(770,488,'● C',20,colors.gold)
  if(scene.note) svg+=wrapped(64,502,local(scene.note,lang),75,20,colors.muted)
  return svg
}
function lines(scene,lang) {
  const all = scene.series.flatMap(s=>s.values)
  const low = scene.min??Math.min(...all), high=scene.max??Math.max(...all), span=high-low||1
  const y=v=>420-(v-low)/span*250
  let svg=''
  for(const yy of [170,232,295,357,420]) svg+=line(70,yy,870,yy)
  for(const [p,label] of scene.levels??[]) svg+=line(70,y(p),870,y(p),colors.muted,'6 6')+text(870,y(p)-9,local(label,lang),19,colors.muted,'end')
  scene.series.forEach((series,j)=>{
    const color = series.color??[colors.up,colors.blue,colors.gold,colors.purple][j]
    const coords=series.values.map((v,i)=>[80+i*770/(series.values.length-1),y(v)])
    svg+=pathLine(coords,color)
    if(scene.points) coords.forEach(([x,yy])=>{svg+=circle(x,yy,5,color)})
    svg+=rect(70+j*215,477,18,5,color)+wrapped(98+j*215,486,local(series.label,lang),18,18,color)
  })
  if(scene.axis) {svg+=text(80,451,local(scene.axis[0],lang),20,colors.muted);svg+=text(850,451,local(scene.axis[1],lang),20,colors.muted,'end')}
  if(scene.note) svg+=text(70,132,local(scene.note,lang),22,colors.muted)
  return svg
}
function columns(scene,lang) {
  const max=Math.max(...scene.values,scene.ref??0)*1.22
  const y=v=>420-v/max*245
  const n=scene.values.length, gap=750/n, w=Math.min(96,gap*.6)
  let svg=line(65,420,880,420)+text(65,137,local(scene.unit??['RELATIVE VOLUME','WOLUMEN WZGLĘDNY'],lang),18,colors.muted)
  scene.values.forEach((v,i)=>{
    const x=95+i*gap
    const color=scene.colors?.[i]??(i===n-1?colors.gold:colors.blue)
    svg+=rect(x,y(v),w,420-y(v),color,4)+text(x+w/2,y(v)-13,String(v),22,color,'middle')
    svg+=wrapped(x+w/2,454,local(scene.labels?.[i]??String(i+1),lang),13,18,colors.muted,'middle')
  })
  if(scene.ref) svg+=line(64,y(scene.ref),880,y(scene.ref),colors.purple,'7 7')+text(880,y(scene.ref)-12,local(scene.refLabel??String(scene.ref),lang),19,colors.purple,'end')
  if(scene.note) svg+=wrapped(64,506,local(scene.note,lang),75,20,colors.muted)
  return svg
}
function range(scene,lang) {
  const y=v=>420-(v-scene.low)/(scene.high-scene.low)*260
  let svg=line(610,160,610,420,colors.muted)
  if(scene.zone) svg+=rect(560,y(scene.zone[1]),100,y(scene.zone[0])-y(scene.zone[1]),colors.up,8,.15)
  for(const [value,label,color] of scene.levels) svg+=line(545,y(value),670,y(value),color??colors.muted,'6 6')+wrapped(690,y(value)+7,local(label,lang),17,21,color??colors.muted)
  if(scene.current!==undefined) svg+=circle(610,y(scene.current),9,colors.gold)
  svg+=wrapped(65,220,local(scene.formula,lang),29,28,colors.ink)
  if(scene.note) svg+=wrapped(65,357,local(scene.note,lang),32,21,colors.muted)
  return svg
}
function flow(scene,lang) {
  const steps=scene.steps, n=steps.length
  const columnsCount=n>4?3:n, rows=Math.ceil(n/columnsCount)
  const w=(832-(columnsCount-1)*24)/columnsCount, h=rows===1?210:125
  let svg=''
  steps.forEach((step,i)=>{
    const x=64+(i%columnsCount)*(w+24), y=rows===1?181:153+Math.floor(i/columnsCount)*156
    svg+=rect(x,y,w,h,colors.panel,14)+circle(x+27,y+30,15,colors.blue)+text(x+27,y+36,i+1,17,colors.bg,'middle')
    svg+=wrapped(x+20,y+76,local(step,lang),Math.floor(w/12),22)
    if(i%columnsCount<columnsCount-1&&i<n-1) svg+=text(x+w+12,y+h/2+7,'›',30,colors.gold,'middle')
  })
  if(scene.note) svg+=wrapped(64,rows===1?446:491,local(scene.note,lang),76,20,colors.muted)
  return svg
}
function anatomy(scene,lang) {
  let svg=''
  const items=scene.items??[[104,112,96,108],[108,112,96,100]]
  items.forEach((bar,i)=>{
    const cx=items.length===1?480:240+i*440, y=v=>413-(v-92)*12
    svg+=candle(cx,bar,y,76)
    for(const [idx,label,color] of [[0,'O',colors.blue],[1,'H',colors.muted],[2,'L',colors.muted],[3,'C',colors.gold]]) {
      const left=idx===0
      svg+=line(cx+(left?-42:42),y(bar[idx]),cx+(left?-93:93),y(bar[idx]),color)+text(cx+(left?-105:105),y(bar[idx])+7,`${label} ${bar[idx]}`,22,color,left?'end':'start')
    }
    if(scene.labels) svg+=wrapped(cx,466,local(scene.labels[i],lang),items.length===1?66:32,20,colors.muted,'middle')
  })
  if(scene.note) svg+=wrapped(64,506,local(scene.note,lang),76,20,colors.muted)
  return svg
}
function render(entry,lang) {
  const title=local(entry.title,lang)
  const draw={chart,lines,columns,range,flow,anatomy}[entry.scene.type]
  if(!draw) throw new Error(`Unknown diagram: ${entry.id}`)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="560" viewBox="0 0 960 560" role="img" aria-labelledby="title desc"><title id="title">${escape(title)}</title><desc id="desc">${escape(local(entry.caption,lang))}</desc><g font-family="Arial, Helvetica, sans-serif">${rect(0,0,960,560,colors.bg,18)}${wrapped(48,55,title,57,29)}${line(48,107,912,107)}${draw(entry.scene,lang)}${text(48,542,lang==='en'?'SCHEMATIC • NOT MARKET DATA':'SCHEMAT • NIE DANE RYNKOWE',13,colors.muted)}${text(912,542,'STOCKPILOT / EDUCATION',13,colors.muted,'end')}</g></svg>\n`
}

// Locate sections by corresponding bilingual heading order; preserve source prose.
function sections(md) {
  return [...md.matchAll(/^#{2,4} .+$/gm)].map(m=>({heading:m[0].trim(),start:m.index,end:m.index+m[0].length}))
}
const clean = md=>md.replace(/\n*<!-- definition-diagrams:[^\n]+ -->[\s\S]*?<!-- \/definition-diagrams -->\n*/g,'\n\n')
function illustrateGlossary(md,lang) {
  const heading=lang==='en'?'## 15. Glossary of abbreviations and distinctions':'## 15. Słownik skrótów i rozróżnień'
  const start=md.indexOf(heading)
  const end=md.indexOf('\n## ',start+heading.length)
  if(start<0||end<0) throw new Error('Missing compendium glossary')
  const ids=['ohlcv-data','spread-body','close-position','up-bar-red-body','effort-result-detail','background-structure','test-process','observation-vs-intent','wfo-bullish','stop-loss','reward-risk']
  let row=0
  const section=md.slice(start,end).replace(/^\|.*$/gm,line=>{
    const cells=line.split('|').slice(1,3).map(s=>s.trim())
    if(row++===0) return `| ${cells.join(' | ')} | ${lang==='en'?'Illustration':'Ilustracja'} |`
    if(row===2) return '|---|---|---|'
    const entry=definitions.find(d=>d.id===ids[row-3])
    if(!entry) throw new Error('Unexpected glossary row')
    return `| ${cells.join(' | ')} | ![${local(entry.title,lang)}](/education/definitions/${entry.id}.${lang}.svg) |`
  })
  if(row!==13) throw new Error('Glossary coverage mismatch')
  return md.slice(0,start)+section+md.slice(end)
}
fs.mkdirSync(destination,{recursive:true})
const ids=new Set()
const grouped=new Map()
for(const entry of definitions) {
  if(ids.has(entry.id)) throw new Error(`Duplicate id: ${entry.id}`)
  ids.add(entry.id)
  for(const lang of ['en','pl']) fs.writeFileSync(path.join(destination,`${entry.id}.${lang}.svg`),render(entry,lang),'utf8')
  const key=`${entry.article}|${entry.section}|${entry.placement??'end'}`
  if(!grouped.has(key)) grouped.set(key,[])
  grouped.get(key).push(entry)
}
for(const article of new Set(definitions.map(d=>d.article))) {
  const documents={}
  for(const lang of ['en','pl']) documents[lang]=clean(fs.readFileSync(path.join(root,`src/content/${article}${lang==='en'?'.en':''}.md`),'utf8')).replace(/\r\n/g,'\n')
  const headings={en:sections(documents.en),pl:sections(documents.pl)}
  if(headings.en.length!==headings.pl.length) throw new Error(`Bilingual heading mismatch: ${article}`)
  for(const lang of ['en','pl']) {
    const insertions=[]
    for(const entries of grouped.values()) {
      const first=entries[0]
      if(first.article!==article) continue
      const index=headings.en.findIndex(h=>h.heading.replace(/^#+ /,'')===first.section)
      if(index<0) throw new Error(`Missing section: ${first.section}`)
      const head=headings[lang][index], next=headings[lang][index+1]?.start??documents[lang].length
      let at=next
      const body=documents[lang].slice(head.end,next)
      if(first.placement==='paragraph') {
        const paragraph=body.match(/^\s*\n([^\n]+)\n/)
        if(!paragraph) throw new Error(`Missing paragraph: ${first.section}`)
        at=head.end+paragraph.index+paragraph[0].length
      }
      if(first.placement==='table') {
        const table=body.match(/^\|.+\n(?:\|.*\n)+/m)
        if(!table) throw new Error(`Missing table: ${first.section}`)
        at=head.end+table.index+table[0].length
      }
      const images=entries.map(entry=>{
        const title=local(entry.title,lang), caption=local(entry.caption,lang)
        const suffix=lang==='en'?'Schematic example. Select the image to enlarge.':'Przykład schematyczny. Kliknij ilustrację, aby ją powiększyć.'
        return `![${title.replace(/\]/g,'')}](/education/definitions/${entry.id}.${lang}.svg "${caption.replace(/"/g,'”')} ${suffix}")`
      }).join('\n\n')
      insertions.push({at,content:`\n<!-- definition-diagrams:${entries[0].id} -->\n${images}\n<!-- /definition-diagrams -->\n\n`})
    }
    let result=documents[lang]
    for(const insertion of insertions.sort((a,b)=>b.at-a.at)) result=result.slice(0,insertion.at)+insertion.content+result.slice(insertion.at)
    if(article==='vsaKompendium') result=illustrateGlossary(result,lang)
    fs.writeFileSync(path.join(root,`src/content/${article}${lang==='en'?'.en':''}.md`),result,'utf8')
  }
}
const manifest=definitions.map(({id,article,section,title})=>({id,article,section,title,files:{en:`/education/definitions/${id}.en.svg`,pl:`/education/definitions/${id}.pl.svg`}}))
fs.writeFileSync(path.join(destination,'manifest.json'),JSON.stringify(manifest,null,2)+'\n')
console.log(`Created ${definitions.length} diagrams in both languages (${definitions.length*2} SVG files).`)
for(const article of new Set(definitions.map(d=>d.article))) console.log(`${article}: ${definitions.filter(d=>d.article===article).length}`)
