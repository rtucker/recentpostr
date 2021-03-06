function recentpostr(blogroll) {
    var outputHTML = [];
    for (var i=0; i<blogroll.length; i++){
        if (blogroll[i].isostamp != "") {
            var timeago = ' <span style="color:#888;font-size:85%;">' + jQuery.timeago(blogroll[i].isostamp) + '</span>';
        } else {
            var timeago = "";
        }
        var bloglink = '<span><b><a style="color: #000;" href="' + blogroll[i].blogurl + '">' + blogroll[i].blogtitle + '</a></b></span>';
        var blogpost = '<span><a href="' + blogroll[i].postlink + '">' + blogroll[i].posttitle + '</a></span>' + timeago;

        var outline = '<li>' + bloglink + '<br>' + blogpost + '</li>';

        outputHTML.push(outline);
    }
    document.getElementById('recentpostr_blogroll').innerHTML = outputHTML.join('');
}
