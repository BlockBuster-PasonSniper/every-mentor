package com.wonjun.mentormatch.dto.application;

import com.wonjun.mentormatch.domain.application.Application;
import com.wonjun.mentormatch.domain.application.ApplicationStatus;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
public class ApplicationResponseDto {
    private final Long id;
    private final Long postId;
    private final String postTitle;
    private final Long menteeId;
    private final String menteeName;
    private final ApplicationStatus status;
    private final LocalDateTime createdAt;

    public ApplicationResponseDto(Application entity) {
        this.id = entity.getId();
        this.postId = entity.getPost().getId();
        this.postTitle = entity.getPost().getTitle();
        this.menteeId = entity.getMentee().getId();
        this.menteeName = entity.getMentee().getName();
        this.status = entity.getStatus();
        this.createdAt = entity.getCreatedAt();
    }
}
