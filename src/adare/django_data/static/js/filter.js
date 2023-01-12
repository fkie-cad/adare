$(document).ready(function () {
    let os_select = $("#id_os");
    let distribution_select = $("#id_distribution");
    let version_select = $("#id_version");
    let experiment_table = $("#experiment_table");
    let columns = [{
        field: 'name',
        title: 'name',
        sortable: true,
      }, {
        field: 'uuid',
        title: 'uuid',
        visible: false,
      }, {
        field: 'timestamp_start',
        title: 'time start',
        sortable: true,
        sorter: 'dateSorter',
        visible: false,
    },
    {
        field: 'timestamp_end',
        title: 'time end',
        sortable: true,
        sorter: 'dateSorter',
        visible: false,
    }, {
        field: 'os',
        title: 'os',
        sortable: true,
    },{
        field: 'distribution',
        title: 'os distribution',
        sortable: true,
    },{
        field: 'version',
        title: 'os version',
        sortable: true,
            visible: false,
    }]
    display_rows();

    $(document).on('change', '#id_os', function (){
        get_distributions();
        if(os_select.val() === ""){
            distribution_select.prop("disabled", true);
        }else{
            distribution_select.prop("disabled", false);
        }
        if(distribution_select.val() === ""){
            version_select.prop("disabled", true);
        }else{
            version_select.prop("disabled", false);
        }
        display_rows();
    });

    $(document).on('change', '#id_distribution', function (){
        get_versions();
        if(distribution_select.val() === "None"){
            version_select.prop("disabled", true);
        }else{
            version_select.prop("disabled", false);
        }
        display_rows();
    });

    $(document).on('change', '#id_version', function (){
       display_rows();
    });

    function get_distributions() {
        $('#id_distribution').children().each(function() {
            if (!$(this).hasClass('default_option')){
                $(this).remove();
            }
        });
        $.ajax({
            type: 'GET',
            url: "../get-distributions/",
            data: {
                os: os_select.val()
            },
            dataType: 'json',
            success: function (response) {
                for (let i = 0; i < response.distributions.length; i++) {
                    $('<option/>', {
                        'id': response.distributions[i],
                        'value':response.distributions[i],
                        'html': response.distributions[i]
                    }).appendTo("#id_distribution");
                }
            }
        })
    }

    function get_versions() {
        $('#id_version').children().each(function() {
            if (!$(this).hasClass('default_option')){
                $(this).remove();
            }
        });
        $.ajax({
            type: 'GET',
            url: "../get-versions/",
            data: {
                os: os_select.val(),
                dist: distribution_select.val(),
            },
            dataType: 'json',
            success: function (response) {
                for (let i = 0; i < response.versions.length; i++) {
                    $('<option/>', {
                        'id': response.versions[i],
                        'value':response.versions[i],
                        'html': response.versions[i]
                    }).appendTo("#id_version");
                }
            }
        })
    }

    function display_rows(){
        experiment_table.bootstrapTable("destroy");
        $.ajax({
            type: 'GET',
            url: "../get-experiments/",
            data: {
                os: os_select.val(),
                dist: distribution_select.val(),
                version_select: version_select.val(),
            },
            dataType: 'json',
            success: function (response) {
                console.log(response['data']);
                experiment_table.bootstrapTable({"columns": columns, data: response['data']});
            }
        })
    }
    function dateSorter(a, b){
        return(new Date(a).getTime() - new Date(b).getTime());
    }
});

