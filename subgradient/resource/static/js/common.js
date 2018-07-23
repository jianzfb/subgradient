String.prototype.replaceAll = function(exp, newStr){
    return this.replace(new RegExp(exp, 'gm'), newStr)
};
String.prototype.format = function(args) {
    var result = this;
    if (arguments.length < 1) {
        return result;
    }

    var data = arguments; // 如果模板参数是数组
    if (arguments.length == 1 && typeof (args) == "object") {
        // 如果模板参数是对象
        data = args;
    }
    for ( var key in data) {
        var value = data[key];
        if (undefined != value) {
            result = result.replaceAll("\\{" + key + "\\}", value);
        }
    }
    return result;
};

function is_int(str){
    var r = /^\+?[1-9][0-9]*$/;　　//正整数
    return r.test(str);
}

function is_float(str){
    var r = /^[-\+]?\d+(\.\d+)?$/;
    return r.test(str)
}