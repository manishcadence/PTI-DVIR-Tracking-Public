import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook, SpreadsheetFile, FileBlob} from '@oai/artifact-tool';

const root=path.resolve(import.meta.dirname,'../..');
const out=path.resolve(process.argv[4] || path.join(root,'outputs/stakeholder_report'));
const col=n=>String.fromCharCode(64+n);
if(process.argv[2]==='verify'){
  await fs.mkdir(out,{recursive:true});
  const file=process.argv[3];
  const book=await SpreadsheetFile.importXlsx(await FileBlob.load(file));
  book.recalculate();
  const schema=JSON.parse(await fs.readFile(path.join(import.meta.dirname,'schema.json'),'utf8'));
  for(let i=0;i<schema.length;i++){
    const [name,headers]=schema[i];
    const preview=await book.render({sheetName:name,range:`A1:${col(headers.length)}10`,scale:1,format:'png'});
    await fs.writeFile(path.join(out,`report-sheet-${i+1}.png`),new Uint8Array(await preview.arrayBuffer()));
  }
  console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',
    options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
  console.log('Verified workbook import and rendered all five report sheets.');
} else {
  const book=Workbook.create();
  const schema=JSON.parse(await fs.readFile(path.join(import.meta.dirname,'schema.json'),'utf8'));
  for(const [name,headers] of schema){
    const sheet=book.worksheets.add(name);
    sheet.showGridLines=false;
    sheet.tabColor='#265f99';
    const end=col(headers.length);
    sheet.getRange(`A1:${end}8`).format.font={name:'Arial',size:10,color:'#172940'};
    sheet.getRange(`A1:${end}8`).format.verticalAlignment='center';
    sheet.getRange('A2').values=[[name]];
    sheet.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:'#172940'};
    sheet.getRange('A2').format.rowHeight=26;
    sheet.getRange('A3').values=[['Reporting period']];
    sheet.getRange('A4').values=[['Source']];
    sheet.getRange('A3:A4').format.font={name:'Arial',size:10,color:'#52647a'};
    sheet.getRange(`A6:${end}6`).values=[headers];
    sheet.getRange(`A6:${end}6`).format={fill:'#265f99',font:{name:'Arial',size:10,bold:true,color:'#ffffff'},
      wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:34};
    sheet.getRange(`A6:${end}6`).format.borders={insideVertical:{style:'thin',color:'#ffffff'}};
    sheet.getRange(`A7:${end}8`).values=[headers.map(()=>''),headers.map(()=>'')];
    sheet.getRange(`A7:${end}8`).format={wrapText:true,verticalAlignment:'center',horizontalAlignment:'left',rowHeight:36};
    sheet.getRange(`A8:${end}8`).format.fill='#f1f5f9';
    for(let j=0;j<headers.length;j++){
      const header=headers[j], letter=col(j+1);
      const width=/name|driver|Vehicles|training|Training|Status|Other crew|category|history/.test(header)?30:18;
      sheet.getRange(`${letter}1:${letter}8`).format.columnWidth=width;
      if(header==='DVIRs (15 days)' || header==='Days off'){
        sheet.getRange(`${letter}7:${letter}8`).setNumberFormat('0');
        sheet.getRange(`${letter}7:${letter}8`).format.horizontalAlignment='right';
      } else if(header==='Last DVIR' || header==='Training date'){
        sheet.getRange(`${letter}7:${letter}8`).setNumberFormat('yyyy-mm-dd');
        sheet.getRange(`${letter}7:${letter}8`).format.horizontalAlignment='center';
      } else {
        sheet.getRange(`${letter}7:${letter}8`).setNumberFormat('@');
      }
      if(header==='PTI training' && !name.startsWith('Co-driver ')){
        sheet.getRange(`${letter}7:${letter}8`).format.horizontalAlignment='center';
      }
    }
    const status=col(headers.indexOf('Status')+1);
    for(const [text,fill,color] of [['No DVIR','#fee2e2','#991b1b'],['Submitted','#dcfce7','#166534'],
      ['Day off','#ede9fe','#5b21b6'],['Training:','#dbeafe','#1e40af'],['Review','#fef3c7','#92400e']]){
      sheet.getRange(`${status}7:${status}8`).conditionalFormats.add('containsText',{text,format:{fill,font:{color,bold:true}}});
    }
    if(headers.includes('Safety status (file)')){
      const safety=col(headers.indexOf('Safety status (file)')+1);
      for(const [value,fill,color] of [['Unsafe','#fee2e2','#991b1b'],['Resolved','#dbeafe','#1e40af'],['Safe','#dcfce7','#166534']]){
        sheet.getRange(`${safety}7:${safety}8`).conditionalFormats.add('cellIs',{
          operator:'equal',formula:`"${value}"`,format:{fill,font:{color,bold:true}}});
      }
    }
    sheet.freezePanes.freezeRows(6);
    sheet.freezePanes.freezeColumns(1);
  }
  book.recalculate();
  await fs.mkdir(path.join(root,'src/resources'),{recursive:true});
  await (await SpreadsheetFile.exportXlsx(book)).save(path.join(root,'src/resources/stakeholder_report_template.xlsx'));
  console.log('Authored five-sheet Excel template.');
}
