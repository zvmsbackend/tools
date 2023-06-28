let timeout;
function heartbeat(offline, pred, fn) {
    let xhr = new XMLHttpRequest();
    xhr.open('GET', '/heartbeat', true);
    xhr.onreadystatechange = function() {
        const json = JSON.parse(xhr.responseText);
        if ((!offline && xhr.status != 200) || !pred(json)) {
            clearTimeout(timeout);
            fn(json);
        }
    }
    xhr.send();
    timeout = setTimeout(() => heartbeat(offline, pred, fn), 10000)
}