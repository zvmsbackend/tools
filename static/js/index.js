let focusedInput;
const emojiSpans = [[8986, 8988], [9193, 9204], [9208, 9211], [9410, 9411], [9748, 9750], [9757, 9758], [9800, 9812], [9823, 9824], [9855, 9856], [9875, 9876], [9889, 9890], [9898, 9900], [9917, 9919], [9924, 9926], [9934, 9936], [9937, 9938], [9939, 9941], [9961, 9963], [9968, 9974], [9975, 9979], [9981, 9982], [9986, 9987], [9989, 9990], [9992, 9998], [9999, 10000], [10002, 10003], [10004, 10005], [10006, 10007], [10013, 10014], [10017, 10018], [10024, 10025], [10035, 10037], [10052, 10053], [10055, 10056], [10060, 10061], [10062, 10063], [10067, 10070], [10071, 10072], [10083, 10085], [10133, 10136], [10145, 10146], [10160, 10161], [10175, 10176], [10548, 10550], [11013, 11016], [11035, 11037], [11088, 11089], [11093, 11094], [12336, 12337], [12349, 12350], [12951, 12952], [12953, 12954], [126980, 126981], [127183, 127184], [127344, 127346], [127358, 127360], [127374, 127375], [127377, 127387], [127489, 127491], [127514, 127515], [127535, 127536], [127538, 127547], [127568, 127570], [127744, 127778], [127780, 127892], [127894, 127896], [127897, 127900], [127902, 127985], [127987, 127990], [127991, 128254], [128255, 128318], [128329, 128335], [128336, 128360], [128367, 128369], [128371, 128379], [128391, 128392], [128394, 128398], [128400, 128401], [128405, 128407], [128420, 128422], [128424, 128425], [128433, 128435], [128444, 128445], [128450, 128453], [128465, 128468], [128476, 128479], [128481, 128482], [128483, 128484], [128488, 128489], [128495, 128496], [128499, 128500], [128506, 128592], [128640, 128710], [128715, 128723], [128736, 128742], [128745, 128746], [128747, 128749], [128752, 128753], [128755, 128763], [129296, 129339], [129340, 129343], [129344, 129350], [129351, 129388], [129408, 129432], [129472, 129473]];
const emoji = document.getElementById('emoji-body');
function addEmoji(code) {
    focusedInput.value += String.fromCodePoint(code);
}
emoji.innerHTML = emojiSpans.map(([start, end]) => {
    let ret = [];
    for (let i = start; i < end; i++) {
        ret.push(`<span onclick="addEmoji(${i})">&#${i}</span>`);
    }
    return ret;
}).join('');
const forbiddenWords = [
    '白术',
    '迪希雅',
    '艾尔海森',
    // '流浪者',
    '纳西妲',
    '妮露',
    '赛诺',
    '提纳里',
    '夜兰',
    '神里绫人',
    '八重神子',
    '申鹤',
    '荒泷一斗',
    '珊瑚宫心海',
    '埃洛伊',
    '雷电将军',
    '宵宫',
    '神里绫华',
    '枫原万叶',
    '优菈',
    '胡桃',
    // '魈', 一个字
    '甘雨',
    '阿贝多',
    '钟离',
    '达达利亚',
    '可莉',
    '温迪',
    '七七',
    '刻晴',
    '派蒙',
    // '琴', 一个字
    '莫娜',
    '迪卢克',
    '绮良良',
    '卡维',
    '米卡',
    '瑶瑶',
    '珐露珊',
    '莱依拉',
    '坎蒂丝',
    '多莉',
    '柯莱',
    '鹿野院平藏',
    '久岐忍',
    '云堇',
    '五郎',
    '托马',
    '九条裟罗',
    '早柚',
    '烟绯',
    '罗莎莉亚',
    '辛焱',
    '迪奥娜',
    '丽莎',
    '凝光',
    '凯亚',
    // '北斗',
    // '安柏', ASOIAF读者震怒
    '班尼特',
    '砂糖',
    '芭芭拉',
    '菲谢尔',
    '行秋',
    '诺艾尔',
    '重云',
    '雷泽',
    // '香菱', 万一是甄香菱呢?
    '原神',
    'GENSHIN',
    '提瓦特'
];
function detectGenshin(input) {
    let value = input.value.toUpperCase();
    for (let word of forbiddenWords) {
        if (value.includes(word)) {
            document.getElementById('container').innerHTML = `<div class="alert alert-danger">
            <div class="card-body">我超, 原!</div>
            </div>`;
            return true;
        }
    }
    return false;
}
for (let input of document.getElementsByTagName('input')) {
    input.addEventListener('keydown', (e) => {
        detectGenshin(input);
    });
    input.addEventListener('click', (e) => {
        focusedInput = input;
    });
}
for (let btn of document.getElementsByTagName('button')) {
    btn.addEventListener('click', (e) => {
        for (let input of document.getElementsByTagName('input')) {
            if (detectGenshin(input)) {
                return;
            }
        }
    });
}
for (let form of document.getElementsByTagName('form')) {
    form.addEventListener('submit', (e) => {
        for (let input of document.getElementsByTagName('input')) {
            if (detectGenshin(input)) {
                e.preventDefault();
                return;
            }
        }
    });
}