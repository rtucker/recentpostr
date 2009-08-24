function recentpostr(blogroll) {
    var outputHTML = [];
    for (var i=0; i<blogroll.length; i++){
        if (blogroll[i].isostamp != "") {
            var timeago = '<br><i><small>' + jQuery.timeago(blogroll[i].isostamp) + '</small></i>';
        } else {
            var timeago = "";
        }
        var bloglink = '<span><b><a href="' + blogroll[i].blogurl + '">' + blogroll[i].blogtitle + '</a></b></span>';
        var blogpost = '<span><a href="' + blogroll[i].posturl + '">' + blogroll[i].posttitle + timeago + '</a></span>';

        var outline = '<li>' + bloglink + blogpost + '</li>';

        outputHTML.push(outline);
    }
    document.getElementById('recentpostr_blogroll').innerHTML = outputHTML.join('');
}
