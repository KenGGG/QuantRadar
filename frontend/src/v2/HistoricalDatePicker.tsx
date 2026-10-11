import {useState} from 'react';
import {DatePicker,InputNumber,Select,Space} from 'antd';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

/** Explicit year/month navigation for long historical backtest ranges. */
export default function HistoricalDatePicker({value,onChange,label}:{value:string,onChange:(value:string)=>void,label:string}){
 const [panel,setPanel]=useState(()=>dayjs(value).locale('zh-cn'));
 return <DatePicker aria-label={label} placeholder="YYYY-MM-DD" value={dayjs(value).locale('zh-cn')} format={['YYYY-MM-DD','YYYY/M/D','YYYYMMDD']} allowClear={false} pickerValue={panel} onPanelChange={date=>setPanel(date)} onOpenChange={open=>{if(open)setPanel(dayjs(value).locale('zh-cn'));}} onChange={date=>{if(date?.isValid()){setPanel(date);onChange(date.format('YYYY-MM-DD'));}}} renderExtraFooter={()=> <Space className="historical-date-jump"><span>跳转：</span><InputNumber aria-label={`${label}年份`} min={1} max={9999} precision={0} value={panel.year()} onChange={year=>{if(year)setPanel(panel.date(1).year(year));}} controls={false} style={{width:76}}/><span>年</span><Select aria-label={`${label}月份`} value={panel.month()+1} options={Array.from({length:12},(_,i)=>({value:i+1,label:`${i+1}月`}))} onChange={month=>setPanel(panel.date(1).month(month-1))} getPopupContainer={trigger=>trigger.parentElement!} style={{width:76}}/></Space>}/>;
}
