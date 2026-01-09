package com.wonjun.mentormatch.dto.application;

import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.application.Application;
import com.wonjun.mentormatch.domain.application.ApplicationStatus;
import com.wonjun.mentormatch.domain.post.Post;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class ApplicationSaveRequestDto {
    private Long postId;

    public Application toEntity(Post post, Member mentee) {
        return Application.builder()
                .post(post)
                .mentee(mentee)
                .status(ApplicationStatus.PENDING) // Default status
                .build();
    }
}
